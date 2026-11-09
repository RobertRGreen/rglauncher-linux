# Verified updates and local rollback

RGLauncher: Linux Edition updates its own per-user software releases. It does not restart Hyprland, replace distribution packages or overwrite user configuration. Existing processes keep running; new launches select the activated release through the stable wrappers. Wrappers must resolve the current release once per launch and disable bytecode writes in that managed tree.

The alpha.2 publisher channel is `https://raw.githubusercontent.com/RobertRGreen/rglauncher-linux/main/updates/prerelease.json`, backed by signed GitHub release artifacts. Initial development used an explicit local signed file feed; the deployed channel uses HTTPS with `allow_file: false`. `rglauncher update status` reports the actual feed, channel, current/previous version, pinned-key fingerprint, rollback hold and last error. The Control Room shows the channel/current/previous version and provides check/install/rollback actions; use the CLI for full trust diagnostics.

The initial publisher key is `share/update-keys/rglauncher-2026.pub`. CLI `trusted_key_sha256` hashes the raw 32-byte Ed25519 key: `6b0174d7b3971efae51447aaac4d8ad16c1ecea8fbfba47f9cd1b92da53b60b4`. The SHA-256 over its PEM **file bytes** is `20507e6951b03677b115f657aa681cf299751b36d61dfd3fc61d6f3e5ed1521d`. These describe the same key in different representations. Establish publisher trust independently before installation; an update feed cannot replace the pinned key.

## Client commands

```sh
rglauncher update status
rglauncher update check
rglauncher update apply
rglauncher update rollback
```

`check` verifies current signed metadata and records its sequence; it does not extract or activate an artifact. `apply` performs all verification and the trusted local preflight before switching. `rollback` selects the locally retained previous release after rechecking its signed receipt and actual file inventory. Closing a UI or interrupting a check is not an instruction to discard user settings.

Channels are explicit: `stable` excludes prerelease versions; `prerelease` also admits versions such as `0.2.0-alpha.1`. Python package version `0.2.0a1` maps to that SemVer release identity; feeds and release directory names use SemVer, not PEP 440 syntax. Build metadata does not increase precedence. Comparisons follow [Semantic Versioning 2.0.0](https://semver.org/).

After an explicit downgrade through local rollback, automatic updates hold that failed version and versions below it. A higher release can update normally. An explicit manual apply can retry the held version and clears the hold after success. The highest installed-version watermark stays recorded, so a newer signed feed cannot silently drive an automatic downgrade. Local rollback can use a previously verified receipt after its original network metadata expires; this is an explicit offline recovery action, not acceptance of expired remote update metadata.

## Trust and activation order

1. Read the locally pinned Ed25519 public key. The network never supplies a replacement trust root. Accept HTTPS, or local `file:` transport only when the client configuration explicitly allows it; reject HTTP, credentials in URLs, remote file hosts and redirect downgrades.
2. Enforce metadata byte limits, parse strict UTF-8 JSON and verify the feed's signature. Validate product/schema, timestamps, monotonically increasing sequence and unique release identities. An unchanged sequence may repeat the identical signed payload; reuse with different contents is rejected.
3. Select an eligible newer SemVer. Fetch the named manifest, match its exact-byte SHA-256 and verify its own Ed25519 signature. Validate its version, lifetime, artifact size/digest and complete path/size/hash/mode inventory.
4. Download into a private temporary directory, with a signed byte ceiling and streaming digest. Verify the complete artifact before decompressing it. Bound expanded data by the signed inventory plus limited header overhead. Only USTAR regular files and necessary directories are accepted; links, device nodes, FIFOs, sparse entries, PAX/GNU extensions, duplicate/unnormalized paths and trailing payloads are rejected. No `extractall` call is used. Python's archive module supports many formats/features that a software release does not need, so this updater intentionally uses a stricter subset than a general [tarfile reader](https://docs.python.org/3/library/tarfile.html).
5. Match every extracted regular file against the exhaustive inventory and permit only modes `0644` and `0755`. A locally supplied `preflight(path)` callback may now inspect/run the verified candidate. It must raise on failure; returning `None` means success. No feed/manifest command, hook or shell expression is executed. Reverify the tree after preflight.
6. Fsync release contents and directory metadata, preserve a signed receipt and write a recovery journal. Atomically replace the `current` symlink with the verified release and retain `previous`. Persist the version watermark and clear the journal. A file lock serializes checks, applies and rollback. Interrupted transactions are reconciled against the actual symlink on the next invocation.

Signatures authenticate publisher authorization and exact software bytes; they do not prove that a release is bug-free. Protect the publisher's private key. The trust model does not defend against an administrator or the same local account replacing its own pinned key/state. An incorrect system clock can also defeat meaningful expiry interpretation. No universal reliability or independent security audit is claimed by passing the deterministic tests.

## Storage and configuration

Defaults use standard XDG directories:

```text
$XDG_DATA_HOME/rglauncher-linux/
  releases/<semver>/    verified software, not user settings
  current -> releases/<semver>
  previous -> releases/<semver>
$XDG_STATE_HOME/rglauncher-linux/
  update-state.json     sequence/version watermarks, status and rollback hold
  update-transaction.json   present only during an activation/recovery
  update.lock
  receipts/<semver>.json    signed manifests for integrity checks/rollback
$XDG_CONFIG_HOME/rglauncher-linux/updates.json
```

When unset, the XDG roots default to `~/.local/share`, `~/.local/state` and `~/.config`. The installer creates `updates.json` with `feed_url`, `public_key`, `allow_file` and `channel`; the updater reads it through the CLI and never rewrites it. Managed data/state directories must belong to the user and not be writable by others. Do not put profiles, recordings, credentials, runtime caches or private HCP state in a release archive.

Managed release files are checked on rollback and after preflight. Stable wrappers and preflight use `-B`/`PYTHONDONTWRITEBYTECODE=1`; generated `__pycache__` or other extra files violate the exact inventory. A manually altered old release is rejected rather than silently used as a trusted rollback target. The updater retains releases and performs no automatic garbage collection; never delete `current` or `previous` targets to save space.

## Signed document contract

An envelope has exactly two fields: `signed` (an object) and `signature` (strict base64 of the 64-byte Ed25519 signature). Sign the project's canonical UTF-8 representation of `signed`: sorted string keys, no insignificant whitespace, `ensure_ascii=False`, JSON booleans/null and integers within ±(2^53−1), with no floats/nonfinite numbers or duplicate keys. This is a documented project format, not a claim to implement every aspect of a general JSON canonicalization standard. Use the shared implementation to avoid serialization disagreement.

Feed signed fields:

| Field | Meaning |
|---|---|
| `schema`, `product` | `1`, `"rglauncher-linux"` |
| `sequence` | Nonnegative integer, monotonically increasing for this installation's pinned publisher/feed; the client channel filters its releases |
| `issued_at`, `expires_at` | Integer Unix seconds; expiry follows issuance, must be future, issuance at most 5 minutes ahead |
| `releases` | List of `{version, manifest_url, manifest_sha256}` objects |

Manifest signed fields:

| Field | Meaning |
|---|---|
| `schema`, `product`, `version` | Matching product/schema and exact feed SemVer identity |
| `issued_at`, `expires_at` | The same timestamp rules |
| `artifact` | `{url, size, sha256, format: "tar.gz"}`; size is exact compressed bytes |
| `files` | Exhaustive list of `{path, size, sha256, mode}`; mode integers are `420`/`493` (`0644`/`0755`) |

URLs may be absolute or relative to their containing document, subject to transport policy. The feed's manifest hash covers the exact envelope file bytes, including any final newline. The artifact hash covers exact gzip bytes. Paths are normalized UTF-8 POSIX-relative paths with no traversal, backslashes, control characters or colon aliases; no component exceeds 255 bytes. Files cannot also serve as parent directories. Empty/unlisted archive directories are not accepted.

Defaults cap feeds at 1MiB, manifests at 4MiB, compressed artifacts at 512MiB, declared extracted content at 1GiB and inventory at 20,000 files. Expanded tar data is additionally limited to the declared file total plus bounded header overhead. These are code/configuration limits, not assertions about every machine's available space.

## Publisher workflow

`tools/sign_release.py` uses [cryptography's Ed25519 implementation](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/); no handwritten cryptography is used. Its helpers can be called by the release builder:

- `generate_key(private_path, public_path)` creates new keys outside the repository, without overwriting existing files. Private key mode is `0600`.
- `build_manifest(payload_root, artifact_path, artifact_url, version, issued_at, expires_at)` computes sorted paths, normalized modes and file/artifact hashes.
- `sign_document(document, key_or_private_path)` returns an envelope.
- `write_signed(document, key_or_private_path, output_path)` atomically writes the canonical envelope plus newline and returns its exact bytes.

CLI subcommands are `generate-key`, `manifest`, `feed` and `sign`; run `--help` for required arguments. Generate keys in a private publisher directory outside source control. Publish only the public key/fingerprint, signed metadata and allowlisted software artifact. Never ship the private key or copy another platform's source/licensing into this free Linux product.

Create a deterministic `tar.gz` using `tarfile.USTAR_FORMAT`, integer timestamps, normalized ownership and file modes, with paths relative to the release root and no enclosing version directory. Avoid fractional mtimes that would require PAX headers. Publish the artifact, then signed manifest, then a signed feed with an increased sequence. Reusing a version for different artifact bytes/files is rejected; metadata-only timestamp/URL refreshes may keep the same content identity. Increase the feed sequence whenever its signed contents change. A public endpoint and key-distribution/rotation process require their own verified deployment; the initial local signed feed does not establish them.

## Automatic checks

The optional user timer requests `rglauncher update apply --automatic` daily, after startup delay and randomized scheduling, with persistent calendar catch-up. Installation is opt-in through `--enable-autoupdate`. The service template's `@RG_LAUNCHER@`, `@DATA_DIR@` and `@STATE_DIR@` markers must be replaced with systemd-escaped resolved paths by the installer, including custom XDG roots. It uses no new privileges, a private temporary directory and read-only home/system views except managed data/state. Configuration remains read-only to the service.

No systemd unit is enabled just by importing this module, running tests or creating a source archive. The parent installer owns the actual configured local feed/timer and must verify their status separately.

## Verification and limits

```sh
python3 -m unittest discover -s tests -p test_update.py -v
```

Tests create temporary keys/feeds outside the source tree and exercise real signed local update, post-verification fixture execution and rollback while a user-config sentinel remains unchanged. Adversarial cases include signatures/digests, JSON ambiguity/types, expiry/replay, SemVer/channels/high-water/rollback hold, transport redirects, path traversal, link/device/extension/sparse/duplicate/incomplete archives, decompression limits, mutation after preflight, modified receipts/trees, locks, and interrupted activation recovery. They use no network, foreground desktop or physical device actions.

Alpha.2 deployment checks additionally passed a fresh HTTPS-only signed bootstrap, downloaded runtime/source archive hashes, actual per-user integration, two-output shelf readiness and a production systemd timer invocation. An actual alpha.1→alpha.2 isolated upgrade/rollback/automatic-hold/manual-reapply preserved its user-configuration sentinel. Physical hotplug, broad hardware/session coverage and independent usability/security studies remain separate work.
