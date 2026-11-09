"""Curated archive and real updater extraction checks, without desktop/network IO."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rglauncher_linux.update import UpdateConfig, UpdateError, Updater, verify_document
from tools.build_release import REQUIRED, build_release, select_files
from tools.sign_release import sign_document, build_manifest


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='rgl-release-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name); self.root = self.base/'repo'; self.root.mkdir()
        for name in REQUIRED:
            self.write(name, b'original\n')
        key = Ed25519PrivateKey.generate()
        self.write('share/update-keys/rglauncher-2026.pub', key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.write('bin/rglauncher', b'#!/bin/sh\nexit 0\n', 0o751)
        self.write('rglauncher_linux/update.py', b'# updater\n', 0o640)

    def write(self, name, data=b'test\n', mode=0o644):
        path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data); path.chmod(mode); return path

    def build(self, name='output', **kw):
        output = self.base/name
        record = build_release(self.root, output, '0.2.0-alpha.1', architecture='x86_64', **kw)
        return output, output/record['artifact']['name'], record

    def test_deterministic_flat_ustar_regular_files_and_normalized_metadata(self):
        a, artifact, record = self.build()
        for file in self.root.rglob('*'):
            os.utime(file, (123456, 123456))
        b, second, other = self.build('second')
        self.assertEqual(artifact.read_bytes(), second.read_bytes())
        self.assertEqual(record, other)
        raw = artifact.read_bytes()
        self.assertEqual(raw[4:8], bytes(4)); self.assertEqual(raw[3], 0)
        stream = gzip.decompress(raw)
        self.assertEqual(stream[257:263], b'ustar\0')
        with tarfile.open(artifact) as archive:
            members = archive.getmembers()
            self.assertEqual([m.name for m in members], sorted(m.name for m in members))
            self.assertTrue(all(m.isreg() and not m.pax_headers for m in members))
            self.assertTrue(all(m.uid == m.gid == m.mtime == 0 and m.uname == m.gname == '' for m in members))
            self.assertEqual(archive.getmember('bin/rglauncher').mode, 0o755)
            self.assertEqual(archive.getmember('rglauncher_linux/update.py').mode, 0o644)

    def test_curated_names_exclude_private_state_keys_tests_and_development(self):
        for name in ('bin/private-key.pem', 'bin/credentials.json', 'share/secrets.txt',
                     '.git/config', 'tests/test_private.py', 'docs/screenshot.png',
                     'dist/release.tar.gz', 'build/log', 'tools/export_components.py',
                     'rglauncher_linux/__pycache__/cli.pyc', 'vscode/previews/night.png'):
            self.write(name, b'NEVER SHIP')
        for kind in ('binary', 'source'):
            names = select_files(self.root, kind)
            self.assertFalse(any(path.endswith(('.pem', '.pyc', '.png')) for path in names))
            self.assertNotIn('tools/export_components.py', names)
            self.assertNotIn('tests/test_private.py', names)

    def test_symlink_parent_leaf_and_hardlink_rejected(self):
        leaf = self.root/'bin/rglauncher'; leaf.unlink(); leaf.symlink_to(self.root/'LICENSE')
        with self.assertRaisesRegex(UpdateError, 'symlink'): self.build()
        leaf.unlink(); os.link(self.root/'LICENSE', leaf)
        with self.assertRaisesRegex(UpdateError, 'regular'): self.build()
        leaf.unlink(); self.write('bin/rglauncher')
        folder = self.root/'share/instrument-score-aether'; moved = self.root/'tokens-real'; folder.rename(moved)
        folder.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(UpdateError, 'symlink'): self.build()

    def test_manifest_inventory_roundtrips_real_signing_and_updater_extraction(self):
        output, artifact, _ = self.build(artifact_url='file:///test/release.tar.gz', issued_at=1790000000, expires_at=1900000000)
        inventory = json.loads((output/'inventory.json').read_text())
        document = json.loads((output/'manifest.unsigned.json').read_text())
        self.assertEqual(document['files'], inventory)
        rebuilt = build_manifest(output/'payload', artifact, 'file:///test/release.tar.gz', '0.2.0-alpha.1', 1790000000, 1900000000)
        self.assertEqual(rebuilt['files'], inventory)
        key = Ed25519PrivateKey.generate()
        signed, _ = verify_document(json.dumps(sign_document(document, key)).encode(), key.public_key())
        pin = self.base/'publisher.pem'
        pin.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        updater = Updater(UpdateConfig(self.base/'data', self.base/'state', 'file:///feed.json', pin, allow_file=True), clock=lambda:1800000000)
        destination = self.base/'extracted'; destination.mkdir()
        temporary = self.base/'temporary'; temporary.mkdir()
        updater._extract(artifact, destination, signed, temporary)
        updater._verify_tree(destination, signed)
        self.assertEqual({p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}, {item['path'] for item in inventory})

    def test_backend_pair_digest_architecture_and_license_checks(self):
        self.write('share/waybar/waybar', b'fake local executable', 0o755)
        with self.assertRaisesRegex(UpdateError, 'together'): self.build()
        backend = {'platform':'linux','architecture':'aarch64','sha256':hashlib.sha256(b'fake local executable').hexdigest()}
        path = self.write('share/waybar/backend.json', json.dumps(backend).encode())
        with self.assertRaisesRegex(UpdateError, 'architecture'): self.build()
        backend['architecture']='x86_64'; path.write_text(json.dumps(backend))
        with self.assertRaisesRegex(UpdateError, 'license'): self.build()
        self.write('packaging/waybar/LICENSE.Waybar')
        backend['sha256']='0'*64; path.write_text(json.dumps(backend))
        with self.assertRaisesRegex(UpdateError, 'digest'): self.build()
        backend['sha256']=hashlib.sha256(b'fake local executable').hexdigest(); path.write_text(json.dumps(backend))
        _, _, record = self.build()
        self.assertEqual(record['compatibility']['backend']['sha256'], backend['sha256'])

    def test_source_recipe_includes_regeneration_sources_excludes_native_binary(self):
        self.write('assets/icons/generate.py'); self.write('assets/icons/LICENSE'); self.write('tools/build_icons.py')
        self.write('share/waybar/waybar', b'native', 0o755); self.write('share/waybar/backend.json', b'{}')
        self.write('packaging/waybar/build.py')
        output, _, record = self.build(kind='source')
        names = {item['path'] for item in json.loads((output/'inventory.json').read_text())}
        self.assertIn('assets/icons/generate.py',names); self.assertIn('tools/build_icons.py',names)
        self.assertIn('assets/icons/LICENSE',names); self.assertIn('packaging/waybar/build.py',names)
        self.assertNotIn('share/waybar/waybar', names); self.assertNotIn('share/waybar/backend.json',names)
        self.assertEqual(record['compatibility']['architectures'],['source'])

    def test_invalid_metadata_output_reuse_and_source_feed_rejected(self):
        self.build()
        with self.assertRaises(FileExistsError): self.build()
        for kw in ({'artifact_url':'https://example.invalid/a'},
                   {'artifact_url':'http://example.invalid/a','issued_at':1,'expires_at':2},
                   {'artifact_url':'https://example.invalid/a','issued_at':2,'expires_at':1},
                   {'kind':'source','artifact_url':'https://example.invalid/a','issued_at':1,'expires_at':2},
                   {'source_revision':'short'}):
            with self.subTest(kw=kw), self.assertRaises(UpdateError): self.build('invalid',**kw)

    def test_private_key_is_rejected_even_under_public_pin_filename(self):
        key = Ed25519PrivateKey.generate()
        self.write('share/update-keys/rglauncher-2026.pub', key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        with self.assertRaisesRegex(UpdateError, 'public key'):
            self.build()


if __name__ == '__main__': unittest.main()
