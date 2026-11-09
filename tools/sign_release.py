#!/usr/bin/env python3
"""Publisher helper for RGLauncher Ed25519 feeds and manifests.

Private keys must be generated outside this source repository. This tool never
publishes, uploads or installs a release. It uses cryptography's Ed25519 API.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rglauncher_linux.update import PRODUCT, SCHEMA, UpdateError, Version, canonical_json, load_json, safe_path, validate_url, verify_document


def read_private(path: Path) -> Ed25519PrivateKey:
    path = Path(path)
    if path.stat().st_mode & 0o077:
        raise UpdateError("Signing private key must not be accessible by group or others")
    data = path.read_bytes()
    key = Ed25519PrivateKey.from_private_bytes(data) if len(data) == 32 else serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise UpdateError("Signing key is not Ed25519")
    return key


def sign_document(document: dict, key: Ed25519PrivateKey | Path) -> dict:
    if not isinstance(key, Ed25519PrivateKey):
        key = read_private(key)
    signature = key.sign(canonical_json(document))
    return {"signed": document, "signature": base64.b64encode(signature).decode("ascii")}


def write_signed(document: dict, key: Ed25519PrivateKey | Path, output: Path) -> bytes:
    data = canonical_json(sign_document(document, key)) + b"\n"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".signed-", dir=output.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return data


def generate_key(private: Path, public: Path):
    private, public = Path(private), Path(public)
    if private.resolve().is_relative_to(ROOT) or public.resolve().is_relative_to(ROOT):
        raise UpdateError("Generate signing keys outside the source repository")
    if private.exists() or public.exists():
        raise UpdateError("Refusing to overwrite an existing signing key")
    private.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    public.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    descriptor = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
    descriptor = os.open(public, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def build_manifest(root: Path, artifact: Path, artifact_url: str, version: str, issued_at: int, expires_at: int) -> dict:
    root, artifact = Path(root), Path(artifact)
    Version(version)
    validate_url(artifact_url, allow_file=True)
    files = []
    for directory, subdirs, names in os.walk(root, followlinks=False):
        for name in subdirs:
            if (Path(directory) / name).is_symlink():
                raise UpdateError("Release roots cannot contain symlinks")
        for name in names:
            path = Path(directory) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise UpdateError("Release roots may contain regular files only")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(64 * 1024):
                    digest.update(chunk)
            files.append({"path": safe_path(path.relative_to(root).as_posix()), "size": info.st_size,
                          "sha256": digest.hexdigest(), "mode": 0o755 if info.st_mode & 0o111 else 0o644})
    digest = hashlib.sha256()
    with artifact.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
    return {"schema": SCHEMA, "product": PRODUCT, "version": version,
            "issued_at": issued_at, "expires_at": expires_at,
            "artifact": {"url": artifact_url, "size": artifact.stat().st_size,
                         "sha256": digest.hexdigest(), "format": "tar.gz"},
            "files": sorted(files, key=lambda item: item["path"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate-key")
    generate.add_argument("--private", type=Path, required=True)
    generate.add_argument("--public", type=Path, required=True)
    sign = commands.add_parser("sign")
    sign.add_argument("--document", type=Path, required=True)
    manifest = commands.add_parser("manifest")
    manifest.add_argument("--root", type=Path, required=True)
    manifest.add_argument("--artifact", type=Path, required=True)
    manifest.add_argument("--artifact-url", required=True)
    manifest.add_argument("--version", required=True)
    feed = commands.add_parser("feed")
    feed.add_argument("--manifest", type=Path, required=True)
    feed.add_argument("--manifest-url", required=True)
    feed.add_argument("--sequence", type=int, required=True)
    for command in (sign, manifest, feed):
        command.add_argument("--private-key", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    for command in (manifest, feed):
        command.add_argument("--issued-at", type=int, default=None)
        command.add_argument("--expires-at", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate-key":
            generate_key(args.private, args.public)
            print("Ed25519 key pair created outside the source tree; keep the private key private.")
            return 0
        if args.command == "sign":
            document = load_json(args.document.read_bytes())
        elif args.command == "manifest":
            document = build_manifest(args.root, args.artifact, args.artifact_url, args.version,
                                      int(time.time()) if args.issued_at is None else args.issued_at, args.expires_at)
        else:
            validate_url(args.manifest_url, allow_file=True)
            content = args.manifest.read_bytes()
            signed, _ = verify_document(content, read_private(args.private_key).public_key())
            document = {"schema": SCHEMA, "product": PRODUCT, "sequence": args.sequence,
                        "issued_at": int(time.time()) if args.issued_at is None else args.issued_at, "expires_at": args.expires_at,
                        "releases": [{"version": signed["version"], "manifest_url": args.manifest_url,
                                      "manifest_sha256": hashlib.sha256(content).hexdigest()}]}
        write_signed(document, args.private_key, args.output)
        print("Signed document written. Nothing was published or installed.")
        return 0
    except (UpdateError, OSError, ValueError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
