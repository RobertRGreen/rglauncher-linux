"""Verified, per-user RGLauncher releases with atomic activation and rollback.

Network metadata never supplies executable hooks. A caller may supply its own
trusted local preflight callback; it runs only after signature and file checks.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from functools import total_ordering
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import tempfile
import time
from typing import Callable
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import zlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PRODUCT = "rglauncher-linux"
SCHEMA = 1
MAX_SAFE_INTEGER = 2**53 - 1
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z")


class UpdateError(RuntimeError):
    """An update failed verification or could not safely complete."""


def _duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UpdateError("Duplicate JSON key")
        result[key] = value
    return result


def _no_float(_value):
    raise UpdateError("Signed JSON does not permit floating-point numbers")


def load_json(data: bytes):
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_duplicates,
                          parse_float=_no_float, parse_constant=_no_float)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise UpdateError("Invalid UTF-8 JSON") from error


def canonical_json(value) -> bytes:
    """Project canonical form: sorted UTF-8 JSON, integers only, no whitespace."""
    def validate(item):
        if item is None or isinstance(item, (str, bool)):
            return
        if type(item) is int and abs(item) <= MAX_SAFE_INTEGER:
            return
        if isinstance(item, list):
            for child in item:
                validate(child)
            return
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            for child in item.values():
                validate(child)
            return
        raise UpdateError("Unsupported canonical JSON value")
    try:
        validate(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (UnicodeError, ValueError, RecursionError) as error:
        raise UpdateError("Invalid canonical JSON") from error


def public_key(path: Path) -> Ed25519PublicKey:
    try:
        if Path(path).stat().st_size > 65536:
            raise UpdateError("Pinned public key is too large")
        data = Path(path).read_bytes()
        key = Ed25519PublicKey.from_public_bytes(data) if len(data) == 32 else serialization.load_pem_public_key(data)
        if not isinstance(key, Ed25519PublicKey):
            raise UpdateError("Pinned key is not Ed25519")
        return key
    except (OSError, ValueError, TypeError) as error:
        raise UpdateError("Cannot load the pinned Ed25519 public key") from error


def verify_document(data: bytes, key: Ed25519PublicKey) -> tuple[dict, dict]:
    envelope = load_json(data)
    if not isinstance(envelope, dict) or set(envelope) != {"signed", "signature"} or not isinstance(envelope["signed"], dict):
        raise UpdateError("Invalid signed envelope")
    try:
        signature = base64.b64decode(envelope["signature"], validate=True)
        if len(signature) != 64:
            raise UpdateError("Invalid Ed25519 signature length")
        key.verify(signature, canonical_json(envelope["signed"]))
    except (InvalidSignature, ValueError, TypeError) as error:
        raise UpdateError("Signature verification failed") from error
    return envelope["signed"], envelope


@total_ordering
class Version:
    def __init__(self, text: str):
        if not isinstance(text, str) or len(text) > 128:
            raise UpdateError("Invalid semantic version")
        match = SEMVER.fullmatch(text)
        if not match:
            raise UpdateError("Invalid semantic version")
        self.text = text
        self.core = tuple(int(match[n]) for n in (1, 2, 3))
        self.pre = tuple(match[4].split(".")) if match[4] else ()
        if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in self.pre):
            raise UpdateError("Numeric prerelease identifiers cannot have leading zeroes")

    def __eq__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self.core == other.core and self.pre == other.pre

    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        if self.core != other.core:
            return self.core < other.core
        if not self.pre or not other.pre:
            return bool(self.pre) and not other.pre
        for left, right in zip(self.pre, other.pre):
            if left == right:
                continue
            if left.isdigit() and right.isdigit():
                return int(left) < int(right)
            if left.isdigit() != right.isdigit():
                return left.isdigit()
            return left < right
        return len(self.pre) < len(other.pre)


def safe_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024:
        raise UpdateError("Invalid release path")
    if "\\" in value or ":" in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise UpdateError("Unsafe release path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")) or str(path) != value:
        raise UpdateError("Release path must be normalized and relative")
    if any(len(part.encode("utf-8")) > 255 for part in path.parts):
        raise UpdateError("Release path component is too long")
    return value


def validate_url(url: str, allow_file: bool = False) -> str:
    if not isinstance(url, str) or any(ord(c) <= 32 for c in url):
        raise UpdateError("Invalid update URL")
    try:
        parsed = urlsplit(url)
        parsed.port  # Reject malformed/invalid ports before any transport access.
    except ValueError as error:
        raise UpdateError("Invalid update URL") from error
    if parsed.username or parsed.password or parsed.fragment:
        raise UpdateError("Credentials and fragments are not allowed in update URLs")
    if parsed.scheme == "https" and parsed.hostname:
        return url
    if parsed.scheme == "file" and allow_file and parsed.netloc in ("", "localhost"):
        if not Path(unquote(parsed.path)).is_absolute() or "\x00" in unquote(parsed.path):
            raise UpdateError("File feed must use an absolute local path")
        return url
    raise UpdateError("Updates require HTTPS or an explicitly enabled local file feed")


def _integer(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_SAFE_INTEGER:
        raise UpdateError(f"Invalid {name}")
    return value


def _digest(value):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise UpdateError("Invalid SHA-256 digest")
    return value


def _header(document, now, check_time=True):
    if document.get("schema") != SCHEMA or type(document.get("schema")) is not int or document.get("product") != PRODUCT:
        raise UpdateError("Unsupported update schema or product")
    issued = _integer(document.get("issued_at"), "issuance time")
    expires = _integer(document.get("expires_at"), "expiry time")
    if expires <= issued:
        raise UpdateError("Expiry must follow issuance")
    if check_time and (issued > now + 300 or expires <= now):
        raise UpdateError("Update metadata is expired or issued in the future")


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, document):
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(canonical_json(document) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class UpdateConfig:
    data_dir: Path
    state_dir: Path
    feed_url: str
    public_key: Path
    allow_file: bool = False
    channel: str = "stable"
    max_feed_bytes: int = 1024 * 1024
    max_manifest_bytes: int = 4 * 1024 * 1024
    max_artifact_bytes: int = 512 * 1024 * 1024
    max_unpacked_bytes: int = 1024 * 1024 * 1024
    max_files: int = 20000
    timeout: float = 20


class Updater:
    def __init__(self, config: UpdateConfig, clock: Callable[[], float] = time.time):
        self.config = config
        self.clock = clock
        self.data = Path(config.data_dir)
        self.state_dir = Path(config.state_dir)
        self.releases = self.data / "releases"
        self.receipts = self.state_dir / "receipts"
        self.state_path = self.state_dir / "update-state.json"
        self.journal_path = self.state_dir / "update-transaction.json"
        self.key = public_key(config.public_key)
        self.fingerprint = hashlib.sha256(self.key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).hexdigest()
        if config.channel not in ("stable", "prerelease"):
            raise UpdateError("Unknown update channel")
        validate_url(config.feed_url, config.allow_file)

    @contextmanager
    def _lock(self):
        for directory in (self.data, self.state_dir, self.releases, self.receipts):
            if directory.is_symlink():
                raise UpdateError("Managed directory cannot be a symlink")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            info = directory.stat()
            if info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise UpdateError("Managed directories must be owned by this user and not writable by others")
        descriptor = os.open(self.state_dir / "update.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise UpdateError("Another update is in progress") from error
            self._recover()
            yield
        finally:
            os.close(descriptor)

    def _state(self):
        if self.state_path.is_symlink():
            raise UpdateError("Unsafe updater state")
        if self.state_path.exists():
            if self.state_path.is_symlink() or self.state_path.stat().st_size > self.config.max_manifest_bytes:
                raise UpdateError("Unsafe updater state")
            state = load_json(self.state_path.read_bytes())
            if not isinstance(state, dict) or state.get("trusted_key") != self.fingerprint:
                raise UpdateError("Updater state does not match the pinned key")
            if type(state.get("schema")) is not int or state.get("schema") != 1 or type(state.get("feed_sequence")) is not int or state["feed_sequence"] < -1:
                raise UpdateError("Invalid updater state")
            if state["feed_sequence"] >= 0:
                _digest(state.get("feed_digest"))
            if state.get("max_version") is not None:
                Version(state["max_version"])
            if state.get("rollback_hold") is not None:
                Version(state["rollback_hold"])
            return state
        return {"schema": 1, "trusted_key": self.fingerprint, "feed_sequence": -1,
                "feed_digest": None, "max_version": None, "rollback_hold": None, "last_error": None}

    def _link(self, name):
        path = self.data / name
        if not path.is_symlink():
            if path.exists():
                raise UpdateError(f"Managed {name} must be a symlink")
            return None
        target = Path(os.readlink(path))
        if target.is_absolute() or len(target.parts) != 2 or target.parts[0] != "releases":
            raise UpdateError("Release symlink points outside managed releases")
        version = target.parts[1]
        Version(version)
        release = self.releases / version
        if release.is_symlink() or not release.is_dir():
            raise UpdateError("Release symlink target is unavailable or unsafe")
        return version

    def _switch_link(self, name, version):
        target = self.data / name
        if target.exists() and not target.is_symlink():
            raise UpdateError("Refusing to replace an unmanaged directory")
        if version is None:
            target.unlink(missing_ok=True)
        else:
            Version(version)
            temporary = self.data / ("." + name + "." + uuid.uuid4().hex)
            try:
                temporary.symlink_to("releases/" + version)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        _fsync_directory(self.data)

    def _response(self, url):
        validate_url(url, self.config.allow_file)
        allow_file = self.config.allow_file
        class Redirect(HTTPRedirectHandler):
            max_redirections = 5
            max_repeats = 2
            def redirect_request(self, request, fp, code, message, headers, newurl):
                validate_url(newurl, allow_file)
                return super().redirect_request(request, fp, code, message, headers, newurl)
        try:
            response = build_opener(Redirect()).open(Request(url, headers={"User-Agent": "RGLauncher-Linux-Updater/1", "Accept-Encoding": "identity"}), timeout=self.config.timeout)
            validate_url(response.geturl(), self.config.allow_file)
            return response
        except UpdateError:
            raise
        except (OSError, ValueError) as error:
            raise UpdateError("Cannot fetch update data") from error

    def _fetch(self, url, limit):
        try:
            with self._response(url) as response:
                data = response.read(limit + 1)
            if len(data) > limit:
                raise UpdateError("Update metadata exceeds its size limit")
            return data
        except (OSError, HTTPException) as error:
            raise UpdateError("Cannot read update data") from error

    def _feed(self, state):
        document, _envelope = verify_document(self._fetch(self.config.feed_url, self.config.max_feed_bytes), self.key)
        _header(document, int(self.clock()))
        sequence = _integer(document.get("sequence"), "feed sequence")
        digest = hashlib.sha256(canonical_json(document)).hexdigest()
        previous = state.get("feed_sequence", -1)
        if sequence < previous or (sequence == previous and state.get("feed_digest") != digest):
            raise UpdateError("Feed replay or sequence equivocation rejected")
        entries = document.get("releases")
        if not isinstance(entries, list) or len(entries) > self.config.max_files:
            raise UpdateError("Invalid release list")
        versions = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise UpdateError("Invalid release entry")
            version = Version(entry.get("version"))
            if version.text in versions:
                raise UpdateError("Duplicate release version")
            versions.add(version.text)
            _digest(entry.get("manifest_sha256"))
            if not isinstance(entry.get("manifest_url"), str) or not entry["manifest_url"]:
                raise UpdateError("Missing manifest URL")
            validate_url(urljoin(self.config.feed_url, entry["manifest_url"]), self.config.allow_file)
        state.update(feed_sequence=sequence, feed_digest=digest, last_checked_at=int(self.clock()), last_error=None)
        _atomic_json(self.state_path, state)
        return document

    def _inventory(self, document, check_time=True):
        _header(document, int(self.clock()), check_time)
        Version(document.get("version"))
        artifact = document.get("artifact")
        if not isinstance(artifact, dict) or artifact.get("format") != "tar.gz":
            raise UpdateError("Only a tar.gz release artifact is supported")
        if _integer(artifact.get("size"), "artifact size", 1) > self.config.max_artifact_bytes:
            raise UpdateError("Artifact exceeds its size limit")
        _digest(artifact.get("sha256"))
        if not isinstance(artifact.get("url"), str) or not artifact["url"]:
            raise UpdateError("Missing artifact URL")
        files = document.get("files")
        if not isinstance(files, list) or not files or len(files) > self.config.max_files:
            raise UpdateError("Invalid file inventory")
        inventory = {}
        total = 0
        parents = set()
        for item in files:
            if not isinstance(item, dict):
                raise UpdateError("Invalid file inventory entry")
            path = safe_path(item.get("path"))
            if path in inventory:
                raise UpdateError("Duplicate inventory path")
            size = _integer(item.get("size"), "file size")
            _digest(item.get("sha256"))
            if type(item.get("mode")) is not int or item["mode"] not in (0o644, 0o755):
                raise UpdateError("Release files must have mode 0644 or 0755")
            total += size
            if total > self.config.max_unpacked_bytes:
                raise UpdateError("Release exceeds its unpacked size limit")
            inventory[path] = item
            parents.update(str(parent) for parent in PurePosixPath(path).parents if str(parent) != ".")
        if set(inventory) & parents:
            raise UpdateError("Inventory file/directory conflict")
        return inventory, parents

    def _manifest(self, entry):
        url = urljoin(self.config.feed_url, entry["manifest_url"])
        data = self._fetch(url, self.config.max_manifest_bytes)
        if hashlib.sha256(data).hexdigest() != entry["manifest_sha256"]:
            raise UpdateError("Manifest digest mismatch")
        document, envelope = verify_document(data, self.key)
        self._inventory(document)
        if document["version"] != entry["version"]:
            raise UpdateError("Manifest version does not match the feed")
        validate_url(urljoin(url, document["artifact"]["url"]), self.config.allow_file)
        return document, envelope, url

    def _candidate(self, feed, current, requested=None):
        entries = [entry for entry in feed["releases"]
                   if self.config.channel == "prerelease" or not Version(entry["version"]).pre]
        if requested is not None:
            Version(requested)
            entries = [entry for entry in entries if entry["version"] == requested]
            if not entries:
                raise UpdateError("Requested version is unavailable on this channel")
        entries.sort(key=lambda entry: Version(entry["version"]), reverse=True)
        if not entries:
            return None
        candidate = entries[0]
        if current is not None and Version(candidate["version"]) <= Version(current):
            if requested is not None and Version(candidate["version"]) < Version(current):
                raise UpdateError("Remote downgrade rejected; use explicit local rollback")
            return None
        return candidate

    def _download(self, url, target, artifact):
        digest = hashlib.sha256()
        count = 0
        try:
            with self._response(url) as response, target.open("xb") as output:
                while chunk := response.read(64 * 1024):
                    count += len(chunk)
                    if count > artifact["size"]:
                        raise UpdateError("Artifact is larger than its signed size")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        except (OSError, HTTPException) as error:
            raise UpdateError("Cannot download release artifact") from error
        if count != artifact["size"] or digest.hexdigest() != artifact["sha256"]:
            raise UpdateError("Artifact size or digest mismatch")

    def _extract(self, artifact, destination, document, temporary):
        inventory, expected_dirs = self._inventory(document)
        tar_path = temporary / "release.tar"
        # Bound decompression before any tar parser can allocate PAX/GNU metadata.
        maximum = sum(item["size"] for item in inventory.values()) + max(1024 * 1024, len(inventory) * 4096)
        count = 0
        try:
            inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
            with artifact.open("rb") as source, tar_path.open("xb") as output:
                while compressed := source.read(64 * 1024):
                    if inflater.eof:
                        raise UpdateError("Unexpected trailing gzip data")
                    pending = compressed
                    while True:
                        chunk = inflater.decompress(pending, 64 * 1024)
                        pending = inflater.unconsumed_tail
                        count += len(chunk)
                        if count > maximum:
                            raise UpdateError("Expanded tar stream exceeds its limit")
                        output.write(chunk)
                        if inflater.eof:
                            if inflater.unused_data:
                                raise UpdateError("Concatenated gzip members are forbidden")
                            break
                        if not pending and len(chunk) < 64 * 1024:
                            break
                if not inflater.eof:
                    raise UpdateError("Truncated gzip stream")
            seen = set()
            found = set()
            headers = 0
            with tar_path.open("rb") as source:
                while True:
                    header = source.read(512)
                    if len(header) != 512:
                        raise UpdateError("Truncated tar header")
                    if header == bytes(512):
                        if source.read(512) != bytes(512):
                            raise UpdateError("Invalid tar terminator")
                        while tail := source.read(64 * 1024):
                            if any(tail):
                                raise UpdateError("Unexpected trailing archive data")
                        break
                    headers += 1
                    if headers > self.config.max_files * 2 + 1024:
                        raise UpdateError("Too many archive members")
                    if header[257:263] != b"ustar\x00":
                        raise UpdateError("Release must use USTAR headers")
                    member = tarfile.TarInfo.frombuf(header, "utf-8", "strict")
                    if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE):
                        raise UpdateError("Links, devices, sparse, PAX and GNU extension members are forbidden")
                    path = safe_path(member.name.rstrip("/") if member.isdir() else member.name)
                    if path in seen:
                        raise UpdateError("Duplicate archive member")
                    seen.add(path)
                    target = destination / path
                    if member.isdir():
                        if path not in expected_dirs or member.size or member.mode != 0o755:
                            raise UpdateError("Unexpected archive directory")
                        target.mkdir(parents=True, exist_ok=True, mode=0o755)
                        continue
                    expected = inventory.get(path)
                    if expected is None or member.size != expected["size"] or member.mode != expected["mode"]:
                        raise UpdateError("Archive member does not match signed inventory")
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                    digest = hashlib.sha256()
                    remaining = member.size
                    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(descriptor, "wb") as output:
                        while remaining:
                            chunk = source.read(min(64 * 1024, remaining))
                            if not chunk:
                                raise UpdateError("Truncated archive file")
                            remaining -= len(chunk)
                            digest.update(chunk)
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    if digest.hexdigest() != expected["sha256"]:
                        raise UpdateError("Extracted file digest mismatch")
                    os.chmod(target, expected["mode"])
                    padding = (-member.size) % 512
                    if len(source.read(padding)) != padding:
                        raise UpdateError("Truncated archive padding")
                    found.add(path)
            if found != set(inventory):
                raise UpdateError("Archive inventory is incomplete")
        except UpdateError:
            raise
        except (OSError, EOFError, UnicodeError, tarfile.TarError, ValueError, zlib.error) as error:
            raise UpdateError("Invalid or unsafe release archive") from error

    def _verify_tree(self, root, document):
        inventory, parents = self._inventory(document, check_time=False)
        if root.is_symlink() or not root.is_dir():
            raise UpdateError("Release directory is unavailable")
        found = set()
        for directory, subdirs, files in os.walk(root, followlinks=False):
            for name in subdirs:
                path = Path(directory) / name
                if path.is_symlink() or path.relative_to(root).as_posix() not in parents:
                    raise UpdateError("Unexpected directory or link in managed release")
            for name in files:
                path = Path(directory) / name
                info = path.lstat()
                relative = path.relative_to(root).as_posix()
                expected = inventory.get(relative)
                if not stat.S_ISREG(info.st_mode) or expected is None or info.st_nlink != 1:
                    raise UpdateError("Unexpected file or link in managed release")
                if info.st_size != expected["size"] or stat.S_IMODE(info.st_mode) != expected["mode"]:
                    raise UpdateError("Managed release file changed")
                digest = hashlib.sha256()
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(descriptor, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or opened.st_ino != info.st_ino:
                        raise UpdateError("Managed release file changed during verification")
                    while chunk := stream.read(64 * 1024):
                        digest.update(chunk)
                if digest.hexdigest() != expected["sha256"]:
                    raise UpdateError("Managed release integrity mismatch")
                found.add(relative)
        if found != set(inventory):
            raise UpdateError("Managed release inventory is incomplete")

    def _receipt(self, version):
        path = self.receipts / (version + ".json")
        if path.is_symlink() or not path.is_file() or path.stat().st_size > self.config.max_manifest_bytes:
            raise UpdateError("Verified rollback receipt is unavailable")
        document, envelope = verify_document(path.read_bytes(), self.key)
        if document.get("version") != version:
            raise UpdateError("Receipt version mismatch")
        self._verify_tree(self.releases / version, document)
        return document, envelope

    def _recover(self):
        if not self.journal_path.exists():
            return
        if self.journal_path.is_symlink() or self.journal_path.stat().st_size > self.config.max_manifest_bytes:
            raise UpdateError("Unsafe update journal")
        journal = load_json(self.journal_path.read_bytes())
        if not isinstance(journal, dict) or set(journal) != {"kind", "from", "to", "previous"} or journal.get("kind") not in ("apply", "rollback"):
            raise UpdateError("Invalid update journal")
        Version(journal["to"])
        for name in ("from", "to", "previous"):
            if journal.get(name) is not None:
                Version(journal[name])
        current = self._link("current")
        if current == journal["to"]:
            self._receipt(current)
            self._switch_link("previous", journal["from"])
            state = self._state()
            if journal["kind"] == "apply" and (not state.get("max_version") or Version(current) > Version(state["max_version"])):
                state["max_version"] = current
            state["rollback_hold"] = (journal["from"] if journal["kind"] == "rollback" and journal["from"]
                                      and Version(current) < Version(journal["from"]) else None)
            state.update(last_error=None, last_activated_at=int(self.clock()))
            _atomic_json(self.state_path, state)
        elif current == journal["from"]:
            self._switch_link("previous", journal["previous"])
        else:
            raise UpdateError("Interrupted update needs manual recovery: current release changed")
        self.journal_path.unlink()
        _fsync_directory(self.state_dir)

    def _activate(self, version, state, kind):
        before, previous = self._link("current"), self._link("previous")
        _atomic_json(self.journal_path, {"kind": kind, "from": before, "to": version, "previous": previous})
        self._switch_link("previous", before)
        self._switch_link("current", version)
        if kind == "apply" and (not state.get("max_version") or Version(version) > Version(state["max_version"])):
            state["max_version"] = version
        state["rollback_hold"] = before if kind == "rollback" and before and Version(version) < Version(before) else None
        state.update(last_error=None, last_activated_at=int(self.clock()))
        _atomic_json(self.state_path, state)
        self.journal_path.unlink()
        _fsync_directory(self.state_dir)

    def _error(self, state, error):
        state["last_error"] = str(error)
        _atomic_json(self.state_path, state)

    def status(self):
        with self._lock():
            state = self._state()
            return {"current_version": self._link("current"), "previous_version": self._link("previous"),
                    "channel": self.config.channel, "feed_url": self.config.feed_url,
                    "allow_file": self.config.allow_file, "trusted_key_sha256": self.fingerprint,
                    "highest_version": state.get("max_version"), "feed_sequence": state.get("feed_sequence"),
                    "held_version": state.get("rollback_hold"),
                    "last_checked_at": state.get("last_checked_at"), "last_error": state.get("last_error")}

    def check(self):
        with self._lock():
            state = self._state()
            try:
                current = self._link("current")
                feed = self._feed(state)
                entry = self._candidate(feed, current)
                if entry:
                    if state.get("max_version") and Version(entry["version"]) < Version(state["max_version"]):
                        raise UpdateError("Release downgrade below the installed high-water mark rejected")
                    self._manifest(entry)
                return {"current_version": current, "available_version": entry["version"] if entry else None,
                        "channel": self.config.channel, "feed_url": self.config.feed_url,
                        "held_version": state.get("rollback_hold"),
                        "automatic_update_held": bool(entry and state.get("rollback_hold") and Version(entry["version"]) <= Version(state["rollback_hold"])),
                        "feed_sequence": feed["sequence"], "update_available": entry is not None}
            except UpdateError as error:
                self._error(state, error)
                raise

    def apply(self, version=None, preflight=None, automatic=False):
        with self._lock():
            state = self._state()
            try:
                current = self._link("current")
                feed = self._feed(state)
                entry = self._candidate(feed, current, version)
                if entry is None:
                    return {"changed": False, "current_version": current, "channel": self.config.channel, "feed_url": self.config.feed_url}
                target_version = entry["version"]
                if state.get("max_version") and Version(target_version) < Version(state["max_version"]):
                    raise UpdateError("Remote downgrade below the installed high-water mark rejected")
                if automatic and state.get("rollback_hold") and Version(target_version) <= Version(state["rollback_hold"]):
                    return {"changed": False, "current_version": current, "reason": "rollback_hold",
                            "held_version": state["rollback_hold"], "channel": self.config.channel, "feed_url": self.config.feed_url}
                document, envelope, manifest_url = self._manifest(entry)
                receipt = self.receipts / (target_version + ".json")
                if receipt.is_symlink():
                    raise UpdateError("Unsafe existing receipt")
                if receipt.exists():
                    if receipt.stat().st_size > self.config.max_manifest_bytes:
                        raise UpdateError("Existing receipt exceeds its size limit")
                    old, _ = verify_document(receipt.read_bytes(), self.key)
                    def identity(value):
                        fields = {k: value["artifact"][k] for k in ("sha256", "size", "format")}
                        files = sorted(value["files"], key=lambda item: item["path"])
                        return canonical_json({"product": value["product"], "version": value["version"], "artifact": fields, "files": files})
                    if identity(old) != identity(document):
                        raise UpdateError("An existing version cannot be republished with different contents")
                destination = self.releases / target_version
                with tempfile.TemporaryDirectory(prefix=".update-", dir=self.data) as temporary_name:
                    temporary = Path(temporary_name)
                    payload = temporary / "payload"
                    payload.mkdir(mode=0o700)
                    artifact = temporary / "release.tar.gz"
                    self._download(urljoin(manifest_url, document["artifact"]["url"]), artifact, document["artifact"])
                    self._extract(artifact, payload, document, temporary)
                    self._verify_tree(payload, document)
                    if preflight is not None:
                        try:
                            preflight(payload)
                        except Exception as error:
                            raise UpdateError("Release preflight failed: " + str(error)) from error
                        self._verify_tree(payload, document)
                    if destination.exists() or destination.is_symlink():
                        self._verify_tree(destination, document)
                    else:
                        for directory, _subdirs, _files in os.walk(payload, topdown=False):
                            _fsync_directory(directory)
                        os.rename(payload, destination)
                        _fsync_directory(self.releases)
                _atomic_json(receipt, envelope)
                self._activate(target_version, state, "apply")
                return {"changed": True, "current_version": target_version, "previous_version": current,
                        "channel": self.config.channel, "feed_url": self.config.feed_url}
            except UpdateError as error:
                self._error(state, error)
                raise
            except OSError as error:
                wrapped = UpdateError("Cannot commit the verified release")
                self._error(state, wrapped)
                raise wrapped from error

    def rollback(self, preflight=None):
        with self._lock():
            state = self._state()
            previous, current = self._link("previous"), self._link("current")
            if previous is None:
                raise UpdateError("No previous release is available")
            try:
                document, _ = self._receipt(previous)
                if preflight is not None:
                    try:
                        preflight(self.releases / previous)
                    except Exception as error:
                        raise UpdateError("Rollback preflight failed: " + str(error)) from error
                    self._verify_tree(self.releases / previous, document)
                self._activate(previous, state, "rollback")
                return {"changed": True, "current_version": previous, "previous_version": current,
                        "channel": self.config.channel, "feed_url": self.config.feed_url}
            except UpdateError as error:
                self._error(state, error)
                raise
