#!/usr/bin/env python3
"""Render and measure the SVG family with native librsvg + Cairo, offscreen.

Creates actual-size contact sheets and individual verification rasters. It does
not install icons, change desktop settings or open a foreground application.
"""
import argparse
import json
import math
from pathlib import Path
import time
import sys

import cairo
import gi
gi.require_version("Rsvg", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Rsvg, Pango, PangoCairo


HERE = Path(__file__).resolve().parent
SIZES = (16, 24, 32, 48)


def color(cr, hexcolor):
    cr.set_source_rgb(*(int(hexcolor[i:i+2], 16) / 255 for i in (1, 3, 5)))


def svg_handle(path, color_override=None):
    data = path.read_text()
    if color_override:
        data = data.replace('<svg ', f'<svg color="{color_override}" ', 1)
    return Rsvg.Handle.new_from_data(data.encode())


def viewport(size):
    area = Rsvg.Rectangle()
    area.x = area.y = 0
    area.width = area.height = size
    return area


def raster(handle, size):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    assert handle.render_document(cr, viewport(size))
    return surface


def text(cr, content, x, y, size, ink, width=None, heading=False):
    layout = PangoCairo.create_layout(cr)
    face = "JetBrainsMono Nerd Font" if heading else "Noto Sans"
    font = Pango.FontDescription.from_string(face)
    font.set_absolute_size(size * Pango.SCALE)
    layout.set_font_description(font)
    layout.set_text(content, -1)
    if width:
        layout.set_width(int(width * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    color(cr, ink)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)


def mode_spec(mode, palette):
    if mode == "dark":
        return "color-dark", palette["color"]["canvas"], palette["color"]["text"], palette["color"]["secondary"], None
    if mode == "bright":
        return "color-light", palette["icon_light"]["canvas"], palette["icon_light"]["text"], palette["icon_light"]["secondary"], None
    if mode == "symbolic-dark":
        return "symbolic", palette["color"]["canvas"], palette["color"]["text"], palette["color"]["secondary"], palette["color"]["text"]
    return "symbolic", "#e2e2e2", "#171717", "#444444", "#171717"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", type=Path, default=HERE / "generated")
    parser.add_argument("--palette", type=Path, default=HERE / "palette.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    registry = json.loads((args.generated / "registry.json").read_text())
    palette = json.loads(args.palette.read_text())
    icons = registry["icons"]
    measurements = []
    files = []
    start = time.perf_counter()
    for mode in ("dark", "bright", "monochrome", "symbolic-dark"):
        variant, background, ink, secondary, override = mode_spec(mode, palette)
        for size in SIZES:
            sources = {icon["id"]: args.generated / (icon.get("sized_files",{}).get(variant,{}).get(str(size)) or icon["files"][variant]) for icon in icons}
            handles = {name: svg_handle(path,override) for name,path in sources.items()}
            cols, cw, ch, top = 10, 140, size + 46, 78
            rows = math.ceil(len(icons) / cols)
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, cols * cw, rows * ch + top + 12)
            cr = cairo.Context(surface)
            color(cr, background)
            cr.paint()
            text(cr, "INSTRUMENT / SCORE AETHER", 20, 15, 18, ink, heading=True)
            text(cr, f"Native librsvg · {size}px actual glyphs · {mode} · {len(icons)} identities", 20, 44, 12, secondary)
            target = args.output / "rasters" / mode / str(size)
            target.mkdir(parents=True, exist_ok=True)
            for i, icon in enumerate(icons):
                handle = handles[icon["id"]]
                image = raster(handle, size)
                png = target / (icon["id"] + ".png")
                image.write_to_png(str(png))
                x, y = i % cols * cw, top + i // cols * ch
                cr.set_source_surface(image, x + (cw - size) / 2, y + 2)
                cr.paint()
                text(cr, icon["id"].removeprefix("aether-"), x + 8, y + size + 10, 10, secondary, width=cw-16)
                intrinsic = 24 if variant == "symbolic" else size
                success, bounds, logical = handle.get_geometry_for_layer(None, viewport(intrinsic))
                assert success
                out = bounds.x < -.01 or bounds.y < -.01 or bounds.x + bounds.width > intrinsic + .01 or bounds.y + bounds.height > intrinsic + .01
                measurements.append({"id": icon["id"], "mode": mode, "size": size,
                                     "ink_units": "native intrinsic units", "intrinsic_size": intrinsic, "ink": {"x": bounds.x, "y": bounds.y, "width": bounds.width, "height": bounds.height},
                                     "outside_viewport": out})
            path = args.output / f"contact-{mode}-{size}.png"
            surface.write_to_png(str(path))
            files.append(str(path))
    large_ids = ["folder", "folder-open", "folder-music", "folder-projects", "computer", "display",
                 "storage", "headphones", "microphone", "audio-console", "camera", "remote"]
    for mode in ("dark", "bright"):
        variant, background, ink, secondary, override = mode_spec(mode, palette)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1040, 884)
        cr = cairo.Context(surface)
        color(cr, background)
        cr.paint()
        text(cr, "OBJECT MATERIAL / 192px NATIVE RENDER", 24, 18, 18, ink, heading=True)
        for i, slug in enumerate(large_ids):
            icon = next(icon for icon in icons if icon["id"] == "aether-" + slug)
            image = raster(svg_handle(args.generated / icon["files"][variant]), 192)
            x, y = i % 4 * 260 + 34, i // 4 * 270 + 72
            cr.set_source_surface(image, x, y)
            cr.paint()
            text(cr, slug, x, y+201, 13, secondary)
        path = args.output / f"objects-large-{mode}.png"
        surface.write_to_png(str(path))
        files.append(str(path))
    # Independently paint EVERY generated SVG, including all scalable files,
    # not only the subset appearing on the object/contact sheets.
    all_svg = json.loads((args.generated / "files.sha256.json").read_text())
    svg_verification = []
    for relative in all_svg:
        parts = Path(relative).parts
        native_size = int(parts[1]) if len(parts) > 2 and parts[1].isdigit() else 24 if parts[0] == "symbolic" else 96
        image = raster(svg_handle(args.generated/relative), native_size)
        data = image.get_data()
        alpha_index = 3 if sys.byteorder == "little" else 0
        nonzero = sum(int(data[i]) > 0 for i in range(alpha_index, len(data), 4))
        assert nonzero > 0, relative
        svg_verification.append({"file":relative,"size":native_size,"nonzero_alpha_pixels":nonzero})
    (args.output / "all-svg-verification.json").write_text(json.dumps(svg_verification,indent=2)+"\n")
    outside = [m for m in measurements if m["outside_viewport"]]
    report = {"renderer": "librsvg native via GI + Cairo", "version": ".".join(str(getattr(Rsvg, k, "?")) for k in ["MAJOR_VERSION", "MINOR_VERSION", "MICRO_VERSION"]),
              "unique_svg_files_native_rendered": len(svg_verification), "icon_count": len(icons), "svg_count": len(json.loads((args.generated / "files.sha256.json").read_text())), "rendered_rasters": len(measurements),
              "sizes": list(SIZES), "modes": ["dark", "bright", "monochrome", "symbolic-dark"],
              "seconds": round(time.perf_counter()-start, 3), "outside_count": len(outside),
              "outside": outside, "contact_sheets": files, "measurements": measurements}
    (args.output / "render-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in ("measurements", "contact_sheets", "outside")}, indent=2))


if __name__ == "__main__":
    main()
