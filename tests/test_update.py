"""Deterministic trust, archive and transaction tests; no network or desktop IO."""
import base64
from dataclasses import replace
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rglauncher_linux import update
from rglauncher_linux.update import UpdateConfig, UpdateError, Updater, Version, canonical_json, load_json, verify_document
from tools.sign_release import build_manifest, generate_key, sign_document, write_signed


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rglauncher-update-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.feed_dir = self.base / "feed"
        self.feed_dir.mkdir()
        self.key = Ed25519PrivateKey.generate()
        self.pin = self.base / "publisher.pem"
        self.pin.write_bytes(self.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.feed = self.feed_dir / "feed.json"
        self.now = 1_800_000_000
        self.cfg = UpdateConfig(self.base / "data", self.base / "state", self.feed.as_uri(), self.pin, allow_file=True)
        self.service = Updater(self.cfg, clock=lambda: self.now)
        self.entries = {}

    def document(self, **extra):
        return {"schema": 1, "product": "rglauncher-linux", "issued_at": self.now - 1,
                "expires_at": self.now + 3600, **extra}

    def archive(self, members):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for member, content in members:
                archive.addfile(member, io.BytesIO(content) if content is not None else None)
        return gzip.compress(stream.getvalue(), mtime=0)

    def release(self, version="1.0.0", contents=None, members=None, manifest_change=None):
        contents = contents or {"app.py": f'print("{version}")\n'.encode(), "bin/start": b"#!/bin/sh\nexit 0\n"}
        payload = self.base / ("payload-" + version)
        payload.mkdir(exist_ok=True)
        normal = []
        for name, data in contents.items():
            path = payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            mode = 0o755 if name.startswith("bin/") else 0o644
            path.chmod(mode)
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), mode, 0
            normal.append((info, data))
        artifact = self.feed_dir / (version + ".tar.gz")
        artifact.write_bytes(self.archive(normal if members is None else members))
        manifest = build_manifest(payload, artifact, artifact.as_uri(), version, self.now - 1, self.now + 3600)
        if manifest_change:
            manifest_change(manifest)
        self.write_manifest(version, manifest)
        return manifest, artifact

    def write_manifest(self, version, manifest, key=None):
        path = self.feed_dir / (version + ".json")
        data = write_signed(manifest, key or self.key, path)
        self.entries[version] = {"version": version, "manifest_url": path.as_uri(), "manifest_sha256": hashlib.sha256(data).hexdigest()}

    def publish(self, sequence=1, versions=None, change=None, key=None):
        document = self.document(sequence=sequence, releases=[self.entries[v] for v in (versions or self.entries)])
        if change:
            change(document)
        write_signed(document, key or self.key, self.feed)

    def initial(self):
        self.release()
        self.publish()
        return self.service.apply()

    def assert_not_activated(self, callback):
        callback.assert_not_called()
        self.assertFalse((self.cfg.data_dir / "current").exists())

    def test_real_signed_update_and_rollback_preserve_config(self):
        config = self.base / "config" / "preferences.json"
        config.parent.mkdir()
        config.write_text('{"preserve":true}\n')
        invoked = []
        def preflight(path):
            invoked.append(subprocess.run([sys.executable, "-B", str(path / "app.py")], capture_output=True, text=True, check=True).stdout.strip())
        self.release()
        self.publish()
        self.assertEqual(self.service.check()["available_version"], "1.0.0")
        self.assertTrue(self.service.apply(preflight=preflight)["changed"])
        self.assertEqual(os.readlink(self.cfg.data_dir / "current"), "releases/1.0.0")
        self.release("2.0.0")
        self.publish(2)
        self.service.apply(preflight=preflight)
        self.assertEqual(self.service.status()["previous_version"], "1.0.0")
        self.service.rollback(preflight=preflight)
        self.assertEqual(invoked, ["1.0.0", "2.0.0", "1.0.0"])
        self.assertEqual(self.service.status()["current_version"], "1.0.0")
        self.assertEqual(self.service.status()["highest_version"], "2.0.0")
        self.assertEqual(config.read_text(), '{"preserve":true}\n')
        self.assertEqual(self.service.status()["feed_url"], self.feed.as_uri())

    def test_signature_failures_never_preflight_or_extract(self):
        self.release()
        for location in ("feed", "manifest"):
            with self.subTest(location=location):
                other = Ed25519PrivateKey.generate()
                if location == "manifest":
                    manifest = load_json((self.feed_dir / "1.0.0.json").read_bytes())["signed"]
                    self.write_manifest("1.0.0", manifest, other)
                self.publish(key=other if location == "feed" else None)
                callback = Mock()
                with self.assertRaises(UpdateError):
                    self.service.apply(preflight=callback)
                self.assert_not_activated(callback)

    def test_artifact_digest_mismatch_never_preflights(self):
        _manifest, artifact = self.release()
        self.publish()
        artifact.write_bytes(artifact.read_bytes()[:-1] + b"x")
        callback = Mock()
        with self.assertRaisesRegex(UpdateError, "digest"):
            self.service.apply(preflight=callback)
        self.assert_not_activated(callback)

    def test_manifest_digest_mismatch(self):
        self.release()
        self.publish()
        path = self.feed_dir / "1.0.0.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(UpdateError, "Manifest digest"):
            self.service.check()

    def test_metadata_expiry_future_and_version_mismatch(self):
        manifest, _artifact = self.release()
        for value in (self.now, self.now - 100):
            self.publish(change=lambda d: d.update(expires_at=value, issued_at=self.now - 1000))
            with self.assertRaisesRegex(UpdateError, "expired"):
                self.service.check()
        self.publish(change=lambda d: d.update(issued_at=self.now + 301, expires_at=self.now + 4000))
        with self.assertRaisesRegex(UpdateError, "future"):
            self.service.check()
        manifest["version"] = "2.0.0"
        self.write_manifest("1.0.0", manifest)
        self.publish()
        with self.assertRaisesRegex(UpdateError, "version"):
            self.service.apply()

    def test_expired_manifest_is_rejected(self):
        self.release(manifest_change=lambda d: d.update(issued_at=self.now - 100, expires_at=self.now - 1))
        self.publish()
        with self.assertRaisesRegex(UpdateError, "expired"):
            self.service.apply()

    def test_invalid_signed_field_types_fail_closed(self):
        manifest, _ = self.release()
        changes = [lambda d: d.update(sequence=True), lambda d: d.update(schema=True),
                   lambda d: d["releases"][0].update(manifest_url=9),
                   lambda d: d["releases"][0].update(manifest_url=""),
                   lambda d: d.update(releases=[d["releases"][0], d["releases"][0]])]
        for change in changes:
            with self.subTest(change=change):
                self.publish(change=change)
                with self.assertRaises(UpdateError):
                    self.service.check()
        manifest["files"][0]["size"] = False
        self.write_manifest("1.0.0", manifest)
        self.publish(2)
        with self.assertRaises(UpdateError):
            self.service.apply()

    def test_remote_hook_fields_are_never_executed(self):
        marker = self.base / "remote-hook-ran"
        self.release(manifest_change=lambda d: d.update(preflight=f"touch {marker}", postinstall=f"touch {marker}"))
        self.publish()
        self.service.apply()
        self.assertFalse(marker.exists())

    def test_feed_replay_and_same_sequence_equivocation(self):
        self.release()
        self.publish(10)
        self.service.check()
        self.publish(9)
        with self.assertRaisesRegex(UpdateError, "replay"):
            self.service.check()
        self.publish(10, change=lambda d: d.update(expires_at=self.now + 7200))
        with self.assertRaisesRegex(UpdateError, "equivocation"):
            self.service.check()

    def test_semver_and_prerelease_policy(self):
        order = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
        self.assertEqual(sorted(order, key=Version), order)
        self.assertEqual(Version("1.0.0+build.01"), Version("1.0.0"))
        for invalid in ("v1.0.0", "01.0.0", "1.2", "1.0.0-alpha.01", "1.0.0-", "1.0.0a1"):
            with self.subTest(invalid=invalid), self.assertRaises(UpdateError):
                Version(invalid)
        self.release()
        self.release("1.1.0-alpha.1")
        self.publish()
        self.assertEqual(self.service.check()["available_version"], "1.0.0")
        preview = Updater(replace(self.cfg, channel="prerelease"), clock=lambda: self.now)
        self.assertEqual(preview.check()["available_version"], "1.1.0-alpha.1")

    def test_rollback_keeps_remote_version_high_water_mark(self):
        self.initial()
        self.release("3.0.0")
        self.publish(2)
        self.service.apply()
        self.service.rollback()
        self.release("2.0.0")
        self.publish(3, versions=["2.0.0"])
        with self.assertRaisesRegex(UpdateError, "high-water"):
            self.service.apply()
        with self.assertRaises(UpdateError):
            self.service.apply(version="0.9.0")

    def test_rollback_holds_automatic_retry_until_newer_release_or_manual_apply(self):
        self.initial()
        self.release("2.0.0")
        self.publish(2)
        self.service.apply()
        self.service.rollback()
        self.assertEqual(self.service.status()["held_version"], "2.0.0")
        self.assertTrue(self.service.check()["automatic_update_held"])
        self.assertEqual(self.service.apply(automatic=True)["reason"], "rollback_hold")
        self.assertEqual(self.service.status()["current_version"], "1.0.0")
        # Explicit manual retry is allowed; it is not an automatic replay.
        self.service.apply(version="2.0.0")
        self.assertIsNone(self.service.status()["held_version"])
        self.service.rollback()
        self.release("2.0.1")
        self.publish(3)
        self.assertTrue(self.service.apply(automatic=True)["changed"])
        self.assertEqual(self.service.status()["current_version"], "2.0.1")
        self.assertIsNone(self.service.status()["held_version"])

    def test_preflight_failure_or_mutation_keeps_old_release(self):
        self.initial()
        self.release("2.0.0")
        self.publish(2)
        def fail(_path):
            raise RuntimeError("fixture failure")
        with self.assertRaisesRegex(UpdateError, "preflight"):
            self.service.apply(preflight=fail)
        def mutate(path):
            (path / "unlisted.py").write_text("unexpected")
        with self.assertRaisesRegex(UpdateError, "Unexpected file"):
            self.service.apply(preflight=mutate)
        self.assertEqual(self.service.status()["current_version"], "1.0.0")
        self.assertFalse(any(self.cfg.data_dir.glob(".update-*")))

    def test_paths_and_unsupported_modes_rejected_before_preflight(self):
        manifest, _ = self.release()
        for path in ("../escape", "/escape", "a/../escape", "a//b", "a\\b", "a\x00b", "a:b", "./a"):
            with self.subTest(path=path):
                malformed = json.loads(json.dumps(manifest))
                malformed["files"][0]["path"] = path
                self.write_manifest("1.0.0", malformed)
                self.publish(sequence=100 + len(path))
                # Reset the fixture's trusted-sequence state between independent inputs.
                self.service.state_path.unlink(missing_ok=True)
                callback = Mock()
                with self.assertRaises(UpdateError):
                    self.service.apply(preflight=callback)
                self.assert_not_activated(callback)
        manifest["files"][0]["mode"] = 0o4755
        self.write_manifest("1.0.0", manifest)
        self.publish(1000)
        with self.assertRaisesRegex(UpdateError, "mode"):
            self.service.apply()

    def test_tar_links_devices_extensions_and_traversal_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE,
                     tarfile.FIFOTYPE, tarfile.XHDTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_SPARSE):
            with self.subTest(kind=kind):
                member = tarfile.TarInfo("evil")
                member.type, member.linkname, member.mode = kind, "../../outside", 0o644
                self.release(members=[(member, None)])
                self.publish(1000 + kind[0])
                self.service.state_path.unlink(missing_ok=True)
                callback = Mock()
                with self.assertRaises(UpdateError):
                    self.service.apply(preflight=callback)
                self.assert_not_activated(callback)
        traversal = tarfile.TarInfo("../escaped")
        traversal.mode = 0o644
        self.release(members=[(traversal, b"")])
        self.publish(2000)
        with self.assertRaises(UpdateError):
            self.service.apply()
        self.assertFalse((self.base / "escaped").exists())

    def test_tar_extra_missing_duplicate_and_bad_file_hash(self):
        base = tarfile.TarInfo("app.py")
        base.mode, base.size = 0o644, 1
        extra = tarfile.TarInfo("extra")
        extra.mode = 0o644
        variants = [[], [(base, b"x"), (extra, b"")], [(base, b"x"), (base, b"x")], [(base, b"y")]]
        for number, members in enumerate(variants):
            with self.subTest(number=number):
                self.release(contents={"app.py": b"x"}, members=members)
                self.publish(number + 1)
                with self.assertRaises(UpdateError):
                    self.service.apply()
                self.assertFalse((self.cfg.data_dir / "current").exists())

    def test_tar_checksum_trailing_data_and_decompression_limit(self):
        manifest, artifact = self.release(contents={"app.py": b"x"})
        original = gzip.decompress(artifact.read_bytes())
        for index, raw in enumerate([b"X" + original[1:], original + original, bytes(2 * 1024 * 1024)]):
            with self.subTest(index=index):
                blob = gzip.compress(raw, mtime=0)
                artifact.write_bytes(blob)
                manifest["artifact"].update(size=len(blob), sha256=hashlib.sha256(blob).hexdigest())
                self.write_manifest("1.0.0", manifest)
                self.publish(index + 1)
                with self.assertRaises(UpdateError):
                    self.service.apply()

    def test_gzip_truncation_corruption_and_concatenated_members(self):
        manifest, artifact = self.release()
        original = artifact.read_bytes()
        variants = [original[:-4], original + gzip.compress(b"", mtime=0), b"not-gzip", original[:-1] + bytes([original[-1] ^ 1])]
        for number, blob in enumerate(variants):
            with self.subTest(number=number):
                artifact.write_bytes(blob)
                manifest["artifact"].update(size=len(blob), sha256=hashlib.sha256(blob).hexdigest())
                self.write_manifest("1.0.0", manifest)
                self.publish(number + 1)
                with self.assertRaises(UpdateError):
                    self.service.apply()

    def test_resource_limits(self):
        self.release()
        self.publish()
        for limits in ({"max_feed_bytes": 32}, {"max_manifest_bytes": 32}, {"max_artifact_bytes": 16}, {"max_unpacked_bytes": 2}, {"max_files": 1}):
            with self.subTest(limits=limits):
                limited = Updater(replace(self.cfg, **limits), clock=lambda: self.now)
                with self.assertRaises(UpdateError):
                    limited.apply()

    def test_unmanaged_existing_release_is_not_overwritten(self):
        self.initial()
        self.release("2.0.0")
        self.publish(2)
        target = self.service.releases / "2.0.0"
        target.mkdir()
        sentinel = target / "user-file"
        sentinel.write_text("keep")
        with self.assertRaises(UpdateError):
            self.service.apply()
        self.assertEqual(sentinel.read_text(), "keep")
        self.assertEqual(self.service.status()["current_version"], "1.0.0")

    def test_republished_version_with_different_contents_rejected(self):
        self.initial()
        self.release("2.0.0")
        self.publish(2)
        self.service.apply()
        self.service.rollback()
        self.release("2.0.0", contents={"app.py": b'print("changed")\n'})
        self.publish(3)
        with self.assertRaisesRegex(UpdateError, "republished"):
            self.service.apply()
        self.assertEqual(self.service.status()["current_version"], "1.0.0")

    def test_modified_hardlinked_tree_and_missing_inventory_rejected(self):
        self.initial()
        self.release("2.0.0")
        self.publish(2)
        self.service.apply()
        extra = self.service.releases / "1.0.0/copied.py"
        os.link(self.service.releases / "1.0.0/app.py", extra)
        with self.assertRaises(UpdateError):
            self.service.rollback()
        extra.unlink()
        (self.service.releases / "1.0.0/app.py").unlink()
        with self.assertRaises(UpdateError):
            self.service.rollback()

    def test_rollback_rejects_modified_files_and_receipts(self):
        self.initial()
        self.release("2.0.0")
        self.publish(2)
        self.service.apply()
        path = self.service.releases / "1.0.0/app.py"
        original = path.read_bytes()
        path.write_bytes(b"tampered")
        with self.assertRaises(UpdateError):
            self.service.rollback()
        path.write_bytes(original)
        receipt = self.service.receipts / "1.0.0.json"
        receipt.write_bytes(receipt.read_bytes().replace(b'"signature":"', b'"signature":"X'))
        with self.assertRaises(UpdateError):
            self.service.rollback()
        self.assertEqual(self.service.status()["current_version"], "2.0.0")

    def test_explicit_local_rollback_can_use_expired_known_receipt(self):
        self.initial()
        self.release("2.0.0")
        self.publish(2)
        self.service.apply()
        self.now += 100000
        with patch.object(self.service, "_response", side_effect=AssertionError("rollback must remain offline")):
            self.assertEqual(self.service.rollback()["current_version"], "1.0.0")

    def test_lock_rejects_concurrent_operation(self):
        self.release()
        self.publish()
        with self.service._lock():
            with self.assertRaisesRegex(UpdateError, "progress"):
                self.service.check()

    def test_current_link_outside_release_and_nonlink_are_rejected(self):
        self.cfg.data_dir.mkdir()
        current = self.cfg.data_dir / "current"
        current.symlink_to(self.base)
        with self.assertRaisesRegex(UpdateError, "outside"):
            self.service.status()
        current.unlink()
        current.write_text("user file")
        with self.assertRaises(UpdateError):
            self.service.status()
        self.assertEqual(current.read_text(), "user file")

    def test_corrupt_state_and_journal_rejected(self):
        self.initial()
        original = self.service.state_path.read_bytes()
        state = load_json(original)
        state["feed_sequence"] = "wrong"
        self.service.state_path.write_bytes(canonical_json(state))
        with self.assertRaises(UpdateError):
            self.service.status()
        self.service.state_path.unlink()
        self.service.state_path.symlink_to(self.base / "missing")
        with self.assertRaises(UpdateError):
            self.service.status()
        self.service.state_path.unlink()
        self.service.state_path.write_bytes(original)
        self.service.journal_path.write_bytes(canonical_json({"kind": "apply"}))
        with self.assertRaises(UpdateError):
            self.service.status()

    def test_failed_atomic_switch_recovers_previous_link(self):
        self.initial()
        self.release("2.0.0")
        self.publish(2)
        real_replace = os.replace
        def replace_once(source, target):
            if Path(target) == self.cfg.data_dir / "current":
                raise OSError("injected switch failure")
            return real_replace(source, target)
        with patch("rglauncher_linux.update.os.replace", side_effect=replace_once):
            with self.assertRaises(UpdateError):
                self.service.apply()
        status = self.service.status()
        self.assertEqual(status["current_version"], "1.0.0")
        self.assertIsNone(status["previous_version"])
        self.assertFalse(self.service.journal_path.exists())
        self.assertEqual(self.service.apply()["current_version"], "2.0.0")

    def test_crash_after_switch_recovers_high_water_and_receipt(self):
        self.initial()
        self.release("2.0.0")
        self.publish(2)
        class Crash(BaseException):
            pass
        real_atomic = update._atomic_json
        def interrupt(path, document):
            if Path(path) == self.service.state_path and document.get("max_version") == "2.0.0":
                raise Crash()
            return real_atomic(path, document)
        with patch("rglauncher_linux.update._atomic_json", side_effect=interrupt):
            with self.assertRaises(Crash):
                self.service.apply()
        self.assertEqual(os.readlink(self.cfg.data_dir / "current"), "releases/2.0.0")
        self.assertTrue(self.service.journal_path.exists())
        recovered = self.service.status()
        self.assertEqual(recovered["highest_version"], "2.0.0")
        self.assertEqual(recovered["previous_version"], "1.0.0")

    def test_json_ambiguities_and_untrusted_envelopes(self):
        for content in (b'{"a":1,"a":2}', b'{"a":1.0}', b'{"a":NaN}', b'\xff'):
            with self.subTest(content=content), self.assertRaises(UpdateError):
                load_json(content)
        for value in ({"x": 1.5}, {"x": 2**60}, {1: "bad"}):
            with self.assertRaises(UpdateError):
                canonical_json(value)
        for data in (b'{"signed":{},"signature":"bad"}', b'{"signed":{},"signature":null}', b'{"signed":{}}'):
            with self.assertRaises(UpdateError):
                verify_document(data, self.key.public_key())

    def test_transport_and_pin_policy(self):
        for url in ("http://example.test/feed", "ftp://example.test/feed", "file:///tmp/feed", "https://user:secret@example.test/feed", "https://example.test:bad/feed"):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                Updater(replace(self.cfg, feed_url=url, allow_file=False))
        def opener(handler):
            handler.redirect_request(None, None, 302, "", {}, "http://example.test/downgrade")
        with patch("rglauncher_linux.update.build_opener", side_effect=opener):
            with self.assertRaises(UpdateError):
                self.service._response("https://example.test/feed")
        other = Ed25519PrivateKey.generate()
        self.initial()
        self.pin.write_bytes(other.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        with self.assertRaisesRegex(UpdateError, "pinned key"):
            Updater(self.cfg).status()

    def test_signing_tool_end_to_end_and_private_permissions(self):
        private = self.base / "keys/publisher.pem"
        public = self.base / "keys/publisher.pub"
        generate_key(private, public)
        self.assertEqual(private.stat().st_mode & 0o777, 0o600)
        unsigned = self.base / "unsigned.json"
        unsigned.write_bytes(canonical_json(self.document(sequence=1, releases=[])))
        target = self.base / "signed.json"
        subprocess.run([sys.executable, "tools/sign_release.py", "sign", "--document", str(unsigned), "--private-key", str(private), "--output", str(target)], check=True, capture_output=True)
        signed, _ = verify_document(target.read_bytes(), update.public_key(public))
        self.assertEqual(signed["sequence"], 1)
        with self.assertRaises(UpdateError):
            generate_key(private, public)
        with self.assertRaises(UpdateError):
            generate_key(Path("keys-not-allowed/private.pem"), Path("keys-not-allowed/public.pem"))


if __name__ == "__main__":
    unittest.main()
