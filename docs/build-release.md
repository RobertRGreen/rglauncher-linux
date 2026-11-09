# Build and sign a release

The release builder never signs, publishes, installs or executes packaged
applications. Build from reviewed, generic source. Keep signing private keys
outside the repository and outside every staging/output directory. There is no
public feed implied by these commands.

## Runtime artifact

```sh
python3 -B tools/build_release.py --kind binary --version 0.2.0-alpha.4 \
  --architecture x86_64 --output /path/to/new-output
```

The output directory must not already exist. It contains:

- `rglauncher-linux-0.2.0-alpha.4-linux-x86_64.tar.gz`: flat-root runtime archive.
- `payload/`: exact unpacked files used to construct the archive.
- `inventory.json`: sorted path/size/SHA-256/normalized-mode inventory.
- `release-metadata.json`: artifact digest/size, compatibility, version and count.

The explicit allowlist in `tools/build_release.py` includes named runtime
components in bin/, rglauncher_linux/, share/, systemd/, selected docs, the project
license/notices and the native backend's upstream notice. Icon names derive from
the original, checked-in semantic registry. Arbitrary files underneath an
otherwise included directory are not collected. Tests, screenshots, previews,
private state, local capture tools, signing private keys, .git/, dist/, build/ and
__pycache__/ are excluded. New functionality needs an intentional allowlist
amendment; do not replace it with a repository-wide archive command.

The archive contains only regular-file USTAR members, sorted by relative path.
There is no enclosing release directory and no PAX/GNU extension, symlink,
hardlink, device, directory or sparse member. Owners/groups/names and timestamps
are normalized, modes are 0644 or 0755, gzip has no filename and mtime zero.
Identical reviewed input bytes/modes/metadata produce identical bytes with the
same Python/zlib toolchain. Building a native backend with a different compiler
can change its bytes; the archive builder does not claim to solve native compiler
reproducibility across environments.

The default architecture is the build machine's normalized machine name; set it
explicitly for cross packaging. A native backend is accepted only as the pair
`share/waybar/waybar` and `share/waybar/backend.json`, with a matching SHA-256,
platform and architecture plus `packaging/waybar/LICENSE.Waybar`. Its source
revision/features propagate into compatibility metadata. Nothing is executed to
infer compatibility. Build the pinned backend using packaging/waybar/README.md;
the shell/installer owner selects whether to ship it.

## Original icons and source archive

The original MIT geometry/generator, native contour helper, palette snapshot and
license are in assets/icons/. Regenerate both full themes:

```sh
python3 assets/icons/generate.py
python3 tools/build_icons.py assets/icons/generated/registry.json share/icons
python3 -B tools/build_release.py --kind source --version 0.2.0-alpha.4 \
  --output /path/to/new-source-output
```

The source archive is named `rglauncher-linux-0.2.0-alpha.4-source.tar.gz`. It adds
the exact original icon sources/generated registry/SVGs, release/icon/signing
tools, curated native patches/build recipe, VS Code regeneration sources, named
verification tests and Arch recipe. It omits the
architecture-specific native backend and its digest descriptor. It preserves
the usable Python sources, generic defaults and prebuilt icon themes, so a reader
can inspect or regenerate them without personal source directories. Development
preview receipts are intentionally not release payloads. Named source tests are
included for independent verification; runtime archives omit those tests.

Source archives are distribution material, not executable updater candidates.
The builder rejects producing an updater manifest for a source archive.
Third-party system dependencies remain separately packaged and retain their
licenses; see THIRD_PARTY_NOTICES.

## Sign without handing a private key to the builder

Supply the **actual** planned HTTPS artifact URL and explicit validity interval
to produce an unsigned manifest. File URLs are supported only for deliberate
local trust tests; do not publish a development file feed as a public channel.

```sh
python3 -B tools/build_release.py --kind binary --version 0.2.0-alpha.4 \
  --architecture x86_64 --output /path/to/new-publisher-output \
  --artifact-url https://YOUR-REAL-HOST/releases/rglauncher-linux-0.2.0-alpha.4-linux-x86_64.tar.gz \
  --issued-at ACTUAL_UNIX_ISSUANCE --expires-at ACTUAL_UNIX_EXPIRY
python3 tools/sign_release.py sign \
  --document /path/to/new-publisher-output/manifest.unsigned.json \
  --private-key /path/outside/repository/publisher.pem \
  --output /path/to/new-publisher-output/manifest.json
```

Replace the illustrative host/times; no URL or expiry is invented by the tool.
Use `sign_release.py feed` with the signed manifest, actual manifest URL, strictly
increasing sequence and explicit validity interval to prepare a signed feed.
Review before publishing separately. Never place private keys in payload/, the
archive directory or source control. The builder has no private-key argument.

The unsigned document uses the updater's exact canonical inventory and includes
optional signed `compatibility` and `source_revision` fields. The same
compatibility data is in inventoried release.json inside the artifact. Current
schema-1 metadata allows these extra fields: that is **not** proof that every
client enforces them. Activation must use a trusted local preflight that checks
the native backend/platform/library support. Signature/inventory verification
always precedes extraction/execution in the updater; compatibility labels do not
replace cryptographic verification. See docs/updates.md for trust, channel and
rollback behavior.

## Verification

```sh
python3 -B -m unittest tests.test_build_release tests.test_update
```

The builder tests compare deterministic bytes, normalized USTAR headers, exact
inventory, source selection and exclusion, link rejection, native digest/arch/
license handling, and real Ed25519 verification followed by the actual updater's
bounded extractor/tree verifier. They do not publish, use a real signing key,
modify user preferences or launch the desktop.
