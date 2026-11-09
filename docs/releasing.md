# Maintaining and releasing RGLauncher Linux

The [public repository](https://github.com/RobertRGreen/rglauncher-linux) contains
the original source, tests, native backend patches, icon generators and editor
theme sources. The prerelease feed is
`https://raw.githubusercontent.com/RobertRGreen/rglauncher-linux/main/updates/prerelease.json`;
runtime artifacts and signed manifests are published as GitHub release assets.
This guide describes the maintainer's deliberate release procedure. CI never
signs, publishes or authorizes a desktop update.

## Test a reviewed source change

[Source checks](../.github/workflows/ci.yml) runs on Ubuntu 24.04 for main pushes,
ordinary pull requests and manual dispatch. It uses `/usr/bin/python3` with
distribution GI, GTK3/GTK4, Cairo, NumPy and cryptography packages; it does not
rely on a pip environment lacking system GI. Core tests use temporary roots,
fake command callbacks and display-free native CSS parsing. VS Code checks build
the data-only extension and test its colors, icons and archive. Lua geometry is
tested with fake compositor callbacks. No test step needs a live compositor,
network device, audio interface, display server or release signing key.

The checkout action is pinned to official actions/checkout **v7.0.1**, commit
`3d3c42e5aac5ba805825da76410c181273ba90b1`. This tag and commit were checked through
the [official tag API](https://api.github.com/repos/actions/checkout/git/ref/tags/v7.0.1)
and [release](https://github.com/actions/checkout/releases/tag/v7.0.1); the official
action runs on Node 24. Review the upstream release and resolve the exact commit
again when intentionally updating this dependency. Do not substitute a floating
tag or enable privileged `pull_request_target` execution of contributor code.
Workflow permissions are read-only and checkout credentials are not persisted.

Run the local equivalent with system Python and the documented dependencies:

```sh
/usr/bin/python3 -B -m unittest discover -s tests -p 'test_*.py' -v
/usr/bin/python3 -B vscode/build.py --icons-source assets/icons
/usr/bin/python3 -B -m unittest discover -s vscode/tests -p 'test_*.py' -v
```

The explicit `tests/native_render.py`, `tests/native_shelf.py` and native popup
fixture are separate opt-in integration checks. They are not discovered by the
`test_*.py` commands. Perform native compositor/backend QA separately before
publishing. A green source CI run is not a claim that every compositor, hardware
device, physical display or accessibility mode has passed native acceptance.

## Prepare a new immutable version

1. Review code, tests and compatibility limits. Inspect `git diff` and the
   builder's explicit allowlist. Keep private settings, recordings, machine
   identities, caches, test receipts and signing material outside tracked files.
2. Choose a **new** SemVer release identity. Never replace artifacts or change a
   manifest for a version that clients may already have installed. Update
   `rglauncher_linux/__init__.py` and the corresponding PEP 440 version in
   `pyproject.toml` together; for example, SemVer `0.2.0-alpha.3` corresponds to
   `0.2.0a3`. The VS Code extension has its own version and changes only when that
   component is revised. Update user-facing examples and release notes as needed.
3. If icon geometry changes, regenerate `assets/icons/generated` using
   `assets/icons/generate.py`, then rebuild both themes with `tools/build_icons.py`.
   Inspect native actual-size renders privately. Regenerate the VSIX using
   `vscode/build.py` and place its reviewed output at
   `share/vscode/rglauncher-aether.vsix`. Never include development preview logs
   or private desktop screenshots. The two README images are rendered generic
   specimens, not captures of a user's session.
4. Commit and review the intended source. Record its complete revision with
   `git rev-parse HEAD`. A recorded revision must describe the source actually
   built; it does not replace file-inventory hashes.

## Build and verify the exact native backend

The native Waybar backend is not an arbitrary system Waybar executable. Use the
pinned upstream revision and both reviewed patches in
[packaging/waybar](../packaging/waybar/README.md). `build.py` exports committed
upstream source, verifies the helper matches its patch, builds with two jobs and
records source/patch/binary hashes. Its compiler and development dependencies
must already be installed. It never replaces a live binary.

```sh
python3 packaging/waybar/build.py --source /path/to/local/Waybar.git \
  --output /path/to/new-native-build --meson /path/to/meson
```

Review that build and its menu-lifecycle/Lua compatibility tests. Copy only the
verified executable into `share/waybar/waybar`. Create matching
`share/waybar/backend.json` with its exact SHA-256, actual Linux architecture,
upstream revision and implemented features. Preserve both upstream license
locations expected by packaging. Do not guess backend metadata or copy a binary
from another architecture. The release builder verifies the digest/platform/
architecture pair; native dependency and behavior checks remain necessary.
Native compiler builds are source-pinned recipes, not claimed bit-identical
across arbitrary compiler/library versions.

## Build, sign and test before publishing

Use a protected signing private key **outside the repository, build outputs and
release staging directories**, with mode 0600. Never upload it to GitHub, put it
in Actions secrets or add a signing/publish job to this CI workflow. Test keys
are temporary fixtures and must never sign the public channel. Existing public
clients trust `share/update-keys/rglauncher-2026.pub`.

For the current key, these fingerprints deliberately identify different byte
representations:

- SHA-256 of the PEM file: `20507e6951b03677b115f657aa681cf299751b36d61dfd3fc61d6f3e5ed1521d`.
- SHA-256 of the raw 32-byte Ed25519 public key, as shown by client status:
  `6b0174d7b3971efae51447aaac4d8ad16c1ecea8fbfba47f9cd1b92da53b60b4`.

Do not compare a PEM-file digest against a raw-key digest. Verify trust through
an independent trusted route; hosting the key beside an artifact is not by itself
proof of the publisher's identity.

Follow [the deterministic build guide](build-release.md). Use the actual planned
versioned HTTPS GitHub artifact URL and explicit issuance/expiry timestamps to
build the runtime archive, exact inventory and unsigned manifest. Record source
revision and architecture. Build the separate source archive with regenerable
original sources and tests. The builder creates regular-files-only flat USTAR
archives with normalized metadata and gzip mtime zero. Check hashes, notices and
archive contents; the private key is not a builder input.

Sign the unsigned manifest using `tools/sign_release.py sign`. Prepare a feed
using `tools/sign_release.py feed`, the signed manifest's **actual** planned HTTPS
URL, and a sequence strictly greater than every previously published feed. The
feed helper hashes the exact signed manifest bytes. Use explicit validity times
and verify both signatures locally. Its current feed helper emits one release
entry; edit/review a complete unsigned feed deliberately if retaining multiple
architectures or entries. There is no inferred multi-platform publishing service.

Test the signed artifact/manifest/feed through an isolated local `file:` channel
using a matching explicit test configuration. Exercise install, check, update,
new launches, rollback and preservation of unrelated preferences. Run trusted
local preflight and native QA on the actual target platform. Test that modified
bytes or wrong signatures fail before activation. Keep receipts and signing keys
private; source CI alone cannot prove that an uploaded artifact matches this QA.

## Publish assets first, then the feed

1. Create the new versioned GitHub release/tag from reviewed source. Upload the
   finalized runtime archive, source archive, signed manifest and useful checksum
   data. Never overwrite an existing published version to repair a release.
2. Fetch the **public HTTPS** asset URLs, check exact byte SHA-256 values and
   verify the manifest signature against the pinned public key. Confirm its
   artifact URL, byte length, digest, architecture and inventory. Resolve upload
   or redirect problems before advertising it to clients.
3. Publish the new signed `updates/prerelease.json` in main **last**, after all
   referenced bytes are publicly available and verified. A tag or unverified
   release upload does not authorize an update. Keep sequence monotonic; do not
   reuse a sequence with different signed contents.
4. Fetch the raw public feed over HTTPS and verify signature, sequence, validity
   interval and exact manifest digest. Run a client check against that public
   URL, then an explicitly authorized target update. Report the actual installed
   version/channel and limitations; source publication and activation are
   separate events. Do not rewrite a client's configuration to hide a failure.

A failed published release is corrected by a **new higher version and new feed
sequence**. Existing local rollback checks the retained receipt and file tree;
automatic retry holds protect a deliberately rolled-back version. Renew metadata
before expiry using a new signed feed sequence, and renew/version manifests and
artifacts deliberately where their validity requires it. Never instruct users
to weaken signature, expiry, digest or downgrade checks.

## Signing-key rotation

The updater does not accept a replacement trust root from the network. Key
rotation is a separately reviewed manual trust migration: create/protect a new
key outside the repository, distribute and authenticate its public fingerprint
through trusted routes, and explicitly repin/reinstall clients. Merely adding a
new public key to source or signing a feed with it does **not** migrate existing
clients. Publish a clear transition plan; do not claim automatic cross-signing or
rotation support that the client does not implement. Treat a compromised key as
an incident requiring explicit new trust, not an unsigned emergency update.
