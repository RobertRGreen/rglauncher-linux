"""Deterministic VSIX archive writer with a strict data-only allowlist."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
import zipfile


def build_vsix(root):
    package = json.loads((root / "package.json").read_text())
    version = package["version"]
    namespace = "http://schemas.microsoft.com/developer/vsx-schema/2011"
    ET.register_namespace("", namespace)
    element = lambda name, attrs=None: ET.Element("{" + namespace + "}" + name, attrs or {})
    manifest = element("PackageManifest", {"Version": "2.0.0"})
    metadata = element("Metadata")
    manifest.append(metadata)
    metadata.append(element("Identity", {"Language": "en-US", "Id": package["name"], "Version": version, "Publisher": package["publisher"]}))
    for name, value in [("DisplayName", package["displayName"]), ("Description", package["description"]), ("License", "extension/LICENSE"), ("Tags", "Themes,Aether,Instrument,Score")]:
        node = element(name)
        node.text = value
        metadata.append(node)
    properties = element("Properties")
    properties.append(element("Property", {"Id": "Microsoft.VisualStudio.Code.Engine", "Value": package["engines"]["vscode"]}))
    metadata.append(properties)
    targets = element("Installation")
    targets.append(element("InstallationTarget", {"Id": "Microsoft.VisualStudio.Code"}))
    manifest.append(targets)
    manifest.append(element("Dependencies"))
    assets = element("Assets")
    for kind, path in [("Microsoft.VisualStudio.Code.Manifest", "extension/package.json"),
                       ("Microsoft.VisualStudio.Services.Content.Details", "extension/README.md"),
                       ("Microsoft.VisualStudio.Services.Content.Changelog", "extension/CHANGELOG.md"),
                       ("Microsoft.VisualStudio.Services.Content.License", "extension/LICENSE")]:
        assets.append(element("Asset", {"Type": kind, "Path": path, "Addressable": "true"}))
    manifest.append(assets)
    content_types = b'''<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json"/>
  <Default Extension="svg" ContentType="image/svg+xml"/>
  <Default Extension="md" ContentType="text/markdown"/>
  <Default Extension="txt" ContentType="text/plain"/>
  <Default Extension="vsixmanifest" ContentType="text/xml"/>
  <Override PartName="/extension/LICENSE" ContentType="text/plain"/>
  <Override PartName="/extension/icons/LICENSE" ContentType="text/plain"/>
</Types>
'''
    files = {"extension.vsixmanifest": ET.tostring(manifest, encoding="utf-8", xml_declaration=True),
             "[Content_Types].xml": content_types}
    for name in ("package.json", "README.md", "CHANGELOG.md", "LICENSE"):
        files["extension/" + name] = (root / name).read_bytes()
    for directory, suffixes in [("themes", {".json"}), ("icons", {".json", ".svg"})]:
        for path in sorted((root / directory).rglob("*")):
            if path.is_symlink():
                raise RuntimeError("Refuse symlink in extension archive: " + str(path))
            if path.is_file() and path.suffix in suffixes:
                files["extension/" + path.relative_to(root).as_posix()] = path.read_bytes()
    files["extension/icons/LICENSE"] = (root / "icons/LICENSE").read_bytes()
    output = root / "dist" / f"{package['name']}-{version}.vsix"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return output
