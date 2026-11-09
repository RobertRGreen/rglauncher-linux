#!/usr/bin/env python3
"""Reproducible icon-source checks, vector equivalence and optional GTK tinting."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import warnings
import xml.etree.ElementTree as ET

from generate import ICONS, svg
from render import raster
import gi
gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg


HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", type=Path, default=HERE / "generated")
    parser.add_argument("--palette", type=Path, default=HERE / "palette.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gtk-symbolic", action="store_true", help="Requires a display connection, but opens no window")
    args = parser.parse_args()
    registry = json.loads((args.generated / "registry.json").read_text())
    hashes = json.loads((args.generated / "files.sha256.json").read_text())
    palette = json.loads(args.palette.read_text())
    for path, expected in hashes.items():
        text = (args.generated / path).read_text()
        assert hashlib.sha256(text.encode()).hexdigest() == expected, path
        root = ET.fromstring(text)
        assert root.attrib["viewBox"] == "0 0 24 24", path
        assert not any(item in text for item in ("<image", "<text ", "<animate", "<script", "filter=", "href=")), path
        if path.startswith("symbolic/"):
            paths = [e for e in root.iter() if e.tag.endswith("path")]
            assert paths and all(e.attrib.get("fill") == "currentColor" and e.attrib.get("stroke") == "none" for e in paths), path
    geometry = []
    alpha = 3 if sys.byteorder == "little" else 0
    for original, record in zip(ICONS, registry["icons"]):
        assert original["id"] == record["id"]
        before = raster(Rsvg.Handle.new_from_data(svg(original, palette["color"], "symbolic").encode()), 96)
        after = raster(Rsvg.Handle.new_from_data((args.generated / record["files"]["symbolic"]).read_bytes()), 96)
        a, b = before.get_data(), after.get_data()
        difference = sum(abs(int(a[i])-int(b[i])) for i in range(alpha, len(a), 4))
        reference = sum(int(a[i]) for i in range(alpha, len(a), 4))
        relative = difference / reference
        geometry.append({"id":original["id"], "alpha_L1_error_over_reference":relative})
        assert relative < .12, (original["id"], relative)
    tint = []
    if args.gtk_symbolic:
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gio, Gdk
        foreground = Gdk.RGBA()
        foreground.parse("#f2c77d")
        for icon in registry["icons"]:
            path = args.generated / icon["files"]["symbolic"]
            info = Gtk.IconTheme.get_default().lookup_by_gicon(Gio.FileIcon.new(Gio.File.new_for_path(str(path))),24,Gtk.IconLookupFlags.FORCE_SYMBOLIC)
            pixbuf, symbolic = info.load_symbolic(foreground,None,None,None)
            assert symbolic, icon["id"]
            data, channels, stride = pixbuf.get_pixels(), pixbuf.get_n_channels(), pixbuf.get_rowstride()
            pixels = [tuple(data[y*stride+x*channels:y*stride+x*channels+3]) for y in range(pixbuf.get_height()) for x in range(pixbuf.get_width()) if data[y*stride+x*channels+3]>230]
            assert pixels, icon["id"]
            means = [sum(p[c] for p in pixels)/len(pixels) for c in range(3)]
            error = max(abs(a-b) for a,b in zip(means,(242,199,125)))
            assert error < 2, (icon["id"],error)
            tint.append({"id":icon["id"],"max_mean_rgb_error":error})
    result = {"hash_and_structure_files":len(hashes), "symbolic_outline_comparisons":geometry,
              "maximum_outline_error":max(v["alpha_L1_error_over_reference"] for v in geometry),
              "gtk_symbolic_tint_count":len(tint), "gtk_symbolic_tint":tint}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"hash_and_structure_files":len(hashes),"outline_comparisons":len(geometry),
                      "maximum_outline_error":result["maximum_outline_error"],"gtk_symbolic_tint_count":len(tint)},indent=2))


if __name__ == "__main__":
    main()
