"""Self-contained original SVG file icons; no icon font or upstream logos."""
from pathlib import Path
import copy
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
FAMILY = {
    "file": "aether-document", "text": "aether-document-text", "code": "aether-document-code",
    "audio": "aether-document-audio", "image": "aether-document-image", "video": "aether-document-video",
    "table": "aether-document-table", "package": "aether-package", "archive": "aether-archive",
    "settings": "aether-settings", "folder": "aether-folder", "folder_open": "aether-folder-open",
    "folder_music": "aether-folder-music", "folder_docs": "aether-folder-documents",
    "folder_images": "aether-folder-pictures", "folder_projects": "aether-folder-projects",
}

# Project-authored monoline letterforms, not font data or company/language logos.
GLYPHS = {
    "A": "M0 7L2.5 0L5 7M1 4H4", "B": "M0 0V7H3.5Q5 7 5 5.3Q5 3.5 3.5 3.5H0M0 0H3.5Q5 0 5 1.7Q5 3.5 3.5 3.5",
    "C": "M5 1Q4 0 2.5 0Q0 0 0 2V5Q0 7 2.5 7Q4 7 5 6", "D": "M0 0V7H2Q5 7 5 4V3Q5 0 2 0Z",
    "G": "M5 1Q4 0 2.5 0Q0 0 0 2V5Q0 7 2.5 7Q5 7 5 5V3.5H3", "H": "M0 0V7M5 0V7M0 3.5H5",
    "J": "M0 0H5V5Q5 7 2.5 7Q0 7 0 5", "L": "M0 0V7H5", "M": "M0 7V0L2.5 3L5 0V7",
    "O": "M2 0H3Q5 0 5 2V5Q5 7 3 7H2Q0 7 0 5V2Q0 0 2 0Z", "P": "M0 7V0H3.5Q5 0 5 1.5V2Q5 3.5 3.5 3.5H0",
    "R": "M0 7V0H3.5Q5 0 5 1.5V2Q5 3.5 3.5 3.5H0M2.5 3.5L5 7",
    "S": "M5 .5H1Q0 .5 0 1.5V2.5Q0 3.5 1 3.5H4Q5 3.5 5 4.5V5.5Q5 6.5 4 6.5H0",
    "T": "M0 0H5M2.5 0V7", "Y": "M0 0L2.5 3.5L5 0M2.5 3.5V7",
    "+": "M0 3.5H5M2.5 1V6", "#": "M1.5 0L.5 7M4.5 0L3.5 7M0 2.3H5M0 4.7H5",
    "<": "M4 0L0 3.5L4 7", ">": "M1 0L5 3.5L1 7",
    "{": "M4 0H3Q2 0 2 1.5V2Q2 3.5 .5 3.5Q2 3.5 2 5V5.5Q2 7 3 7H4",
    "}": "M1 0H2Q3 0 3 1.5V2Q3 3.5 4.5 3.5Q3 3.5 3 5V5.5Q3 7 2 7H1",
}
BADGES = {"python": "PY", "javascript": "JS", "typescript": "TS", "rust": "RS", "go": "GO",
          "c": "C", "cpp": "C+", "csharp": "C#", "shell": "SH", "json": "{}",
          "html": "<>", "css": "CS", "markdown": "MD", "yaml": "YM"}


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def badge_icon(source, text, light):
    tree = ET.parse(source)
    root = tree.getroot()
    root.find("{" + SVG + "}title").text = "Code file · " + text
    scale = .88 if len(text) > 1 else 1.0
    width = (6 * len(text) - 1) * scale
    group = ET.SubElement(root, "{" + SVG + "}g", {
        "transform": f"translate({(24 - width) / 2:.3f},11.8) scale({scale})",
        "fill": "none", "stroke": "#17263a" if light else "#edf4ff",
        "stroke-width": "1.35", "stroke-linecap": "round", "stroke-linejoin": "round",
    })
    for i, char in enumerate(text):
        ET.SubElement(group, "{" + SVG + "}path", {"d": GLYPHS[char], "transform": f"translate({i * 6},0)"})
    return ET.tostring(root, encoding="unicode") + "\n"


def build_icons(root, source):
    ET.register_namespace("", SVG)
    icons = root / "icons"
    icons.mkdir(exist_ok=True)
    registry_path = source / "generated/registry.json"
    provenance_path = icons / "provenance.json"
    if registry_path.exists():
        registry = json.loads(registry_path.read_text())
        if registry.get("license") != "MIT":
            raise RuntimeError("Original icon family needs explicit MIT provenance before bundling")
        records = {record["id"]: record for record in registry["icons"]}
        provenance = {"family": registry["family"], "version": registry["version"], "license": "MIT",
                      "provenance": registry["provenance"], "assets": []}
        for variant in ("dark", "light"):
            target = icons / variant
            target.mkdir(exist_ok=True)
            for short, icon_id in FAMILY.items():
                record = records[icon_id]
                relative = record.get("sized_files", {}).get("color-" + variant, {}).get("16") or record["files"]["color-" + variant]
                svg = source / "generated" / relative
                shutil.copyfile(svg, target / (short + ".svg"))
                provenance["assets"].append({"icon": icon_id, "variant": variant, "optical_size": 16,
                    "source": relative, "sha256": hashlib.sha256(svg.read_bytes()).hexdigest(),
                    "destination": variant + "/" + short + ".svg"})
        _write_json(provenance_path, provenance)
    elif not provenance_path.exists():
        raise RuntimeError("Supply --icons-source, or retain the extension's bundled original SVG sources")
    # Rebuilding from a standalone checkout reuses the licensed original copies.
    for variant in ("dark", "light"):
        for name, text in BADGES.items():
            (icons / variant / (name + ".svg")).write_text(badge_icon(icons / variant / "file.svg", text, variant == "light"))

    definitions = {"_" + short + "_" + variant: {"iconPath": "./" + variant + "/" + short + ".svg"}
                   for variant in ("dark", "light") for short in (*FAMILY, *BADGES)}
    extension_groups = {
        "python": "py pyw pyi", "javascript": "js jsx mjs cjs", "typescript": "ts tsx mts cts",
        "rust": "rs", "go": "go", "c": "c h", "cpp": "cpp cc cxx hpp hh hxx", "csharp": "cs",
        "shell": "sh bash zsh fish", "json": "json jsonc jsonl", "html": "html htm xhtml vue svelte",
        "css": "css scss sass less", "markdown": "md markdown mdx rst", "yaml": "yaml yml",
        "text": "txt log csvlock", "settings": "toml ini cfg conf properties env lock editorconfig",
        "audio": "wav flac mp3 aiff aif ogg opus m4a mid midi als rpp bwproject",
        "image": "png jpg jpeg gif webp svg ico bmp avif tiff", "video": "mp4 mkv mov webm avi m4v",
        "table": "csv tsv xls xlsx ods", "archive": "zip tar gz bz2 xz zst 7z rar",
        "package": "deb rpm pkg appimage flatpak vsix whl wasm so dll exe bin",
    }
    language_groups = {
        "python": "python", "javascript": "javascript javascriptreact", "typescript": "typescript typescriptreact",
        "rust": "rust", "go": "go", "c": "c", "cpp": "cpp", "csharp": "csharp",
        "shell": "shellscript", "json": "json jsonc", "html": "html vue svelte", "css": "css scss less",
        "markdown": "markdown restructuredtext", "yaml": "yaml", "settings": "ini toml properties dotenv",
        "code": "java kotlin swift ruby php lua perl r julia dart fsharp clojure elixir haskell sql graphql dockerfile",
    }

    def associations(variant):
        ref = lambda short: "_" + short + "_" + variant
        extensions = {extension: ref(short) for short, values in extension_groups.items() for extension in values.split()}
        languages = {language: ref(short) for short, values in language_groups.items() for language in values.split()}
        names = {name: ref("settings") for name in [".gitignore", ".gitattributes", ".editorconfig", ".env", "pyproject.toml", "Cargo.toml", "Makefile", "CMakeLists.txt"]}
        names.update({name: ref("package") for name in ["Dockerfile", "Containerfile", "package-lock.json", "yarn.lock", "uv.lock", "requirements.txt"]})
        names["package.json"] = ref("json")
        folders = {name: ref("folder_projects") for name in ["src", "lib", "app", "components", "tests", "test", ".git", "node_modules", "venv", ".venv"]}
        folders.update({name: ref("folder_music") for name in ["audio", "music", "samples", "stems"]})
        folders.update({name: ref("folder_docs") for name in ["docs", "documents", "documentation"]})
        folders.update({name: ref("folder_images") for name in ["images", "pictures", "screenshots", "assets"]})
        return {"file": ref("file"), "folder": ref("folder"), "folderExpanded": ref("folder_open"),
                "rootFolder": ref("folder_projects"), "rootFolderExpanded": ref("folder_open"),
                "fileExtensions": extensions, "fileNames": names, "languageIds": languages,
                "folderNames": folders, "folderNamesExpanded": {name: ref("folder_open") for name in folders}}

    data = {"$schema": "vscode://schemas/icon-theme", "iconDefinitions": definitions,
            "hidesExplorerArrows": False, "showLanguageModeIcons": True,
            **associations("dark"), "light": associations("light")}
    _write_json(icons / "aether-file-icons.json", data)
    shutil.copy2(root.parent / "LICENSE", icons / "LICENSE")
