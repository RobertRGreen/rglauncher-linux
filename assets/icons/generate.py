#!/usr/bin/env python3
"""Original native SVG icon family for Instrument/Score Aether.

Drawings use a 24-unit optical grid. No third-party icon paths, app logos,
external assets, embedded fonts, filters or animation are included.
This generator creates source outputs only; it never installs a theme.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent


@dataclass
class Shape:
    tag: str
    attrs: dict
    role: str = "line"


def P(d, role="line", **attrs):
    return Shape("path", {"d": d, **attrs}, role)


def R(x, y, w, h, r=0, role="body"):
    return Shape("rect", {"x": x, "y": y, "width": w, "height": h, "rx": r}, role)


def C(x, y, r, role="line"):
    return Shape("circle", {"cx": x, "cy": y, "r": r}, role)


def E(x, y, rx, ry, role="line"):
    return Shape("ellipse", {"cx": x, "cy": y, "rx": rx, "ry": ry}, role)


def L(x1, y1, x2, y2, role="line"):
    return Shape("line", {"x1": x1, "y1": y1, "x2": x2, "y2": y2}, role)


ICONS = []


def add(slug, label, context, shapes, aliases=(), meaning="", state=None):
    ICONS.append({"id": "aether-" + slug, "label": label, "context": context,
                  "shapes": shapes, "aliases": list(aliases),
                  "meaning": meaning or label, "state": state})


def folder(mark=()):
    return [P("M3 7V5.5Q3 4 4.5 4H9L11 6H19.5Q21 6 21 7.5V9", "body"),
            P("M3.5 8H20.5Q22 8 21.7 9.5L20.2 18.5Q20 20 18.5 20H5.5Q4 20 3.8 18.5L2.3 9.5Q2 8 3.5 8Z", "body"),
            P("M5 10H18.5", "accent"), *mark]


def document(mark=()):
    return [P("M5 3H14L19 8V20Q19 21 18 21H5Q4 21 4 20V4Q4 3 5 3Z", "body"),
            P("M14 3V8H19", "accent"), *mark]


def gear():
    points = []
    # Eight short teeth; the inner aperture remains recognizable at 16px.
    for i in range(32):
        angle = math.radians(-95 + i * 360 / 32)
        radius = 9 if i % 4 in (0, 1) else 7.2
        points.append((12 + radius * math.cos(angle), 12 + radius * math.sin(angle)))
    d = "M" + "L".join(f"{x:.3f} {y:.3f}" for x, y in points) + "Z"
    return [P(d, "body"), C(12, 12, 3, "line")]


# Navigation and object identities. Containers appear only when intrinsic to
# the depicted object: an application/window/frame, folder, file or device.
add("library", "Application library", "actions", [R(3, 3, 7, 7, 1.4), R(14, 3, 7, 7, 1.4), R(3, 14, 7, 7, 1.4), R(14, 14, 7, 7, 1.4)],
    ["view-app-grid", "applications-all"], "All applications; not current selection count")
add("recent", "Recent", "actions", [P("M4 8A8.5 8.5 0 1 1 3.5 15"), P("M3 4V9H8", "accent"), P("M12 7V12L15 14")],
    ["document-open-recent", "view-history"], "Recently used objects, with no implied replay")
add("workspace", "Workspace", "places", [R(3, 4, 18, 16, 2), L(10, 4, 10, 20, "accent"), L(10, 12, 21, 12)],
    ["preferences-desktop-workspaces", "view-grid"], "Nonoverlapping regions belonging to one workspace")
add("window", "Window", "places", [P("M8 4H20Q21 4 21 5V15", "accent"), R(3, 8, 15, 12, 1.8), L(3, 12, 18, 12)],
    ["preferences-system-windows", "window"], "Window identity; not automatically a new window action")
add("application", "Application", "apps", [R(3, 4, 18, 16, 2), L(3, 9, 21, 9, "accent"), L(8, 9, 8, 20), L(12, 13, 17, 13), L(12, 16, 16, 16)],
    ["application-x-executable", "application-default-icon"], "Generic app fallback; never replaces a known branded application logo")
add("search", "Search", "actions", [C(10.5, 10.5, 6.5, "body"), L(15.2, 15.2, 21, 21, "accent")], ["system-search", "edit-find"])
add("empty-search", "No matching objects", "status", [C(10, 10, 6, "body"), L(14.5, 14.5, 20.5, 20.5, "accent"), L(7.5, 10, 12.5, 10)],
    [], "Search has no matches; not an error or proof an object does not exist")
add("home", "Home", "places", [P("M3 11L12 3L21 11"), P("M5 10V20H10V14H14V20H19V10", "body")], ["user-home", "go-home"])
add("menu", "Menu", "actions", [L(4, 6, 20, 6), L(4, 12, 16, 12, "accent"), L(4, 18, 20, 18)], ["open-menu", "view-list"])
add("back", "Back", "actions", [P("M14 5L7 12L14 19")], ["go-previous"], "Previous logical destination; adapters may mirror for RTL")
add("forward", "Forward", "actions", [P("M10 5L17 12L10 19")], ["go-next"], "Next logical destination; adapters may mirror for RTL")
add("up", "Up", "actions", [P("M5 14L12 7L19 14")], ["go-up"], "Upward spatial or hierarchical movement; not automatically RTL-mirrored")
add("down", "Down", "actions", [P("M5 10L12 17L19 10")], ["go-down"])
add("more", "More actions", "actions", [C(5, 12, 1.2, "solid"), C(12, 12, 1.2, "solid"), C(19, 12, 1.2, "solid")], ["view-more", "overflow-menu"])

# Actions: no intrinsic backing tile, no color-only distinction.
add("add", "Add", "actions", [L(12, 4, 12, 20), L(4, 12, 20, 12)], ["list-add", "add"])
add("remove", "Remove from collection", "actions", [L(4, 12, 20, 12)], ["list-remove"], "Remove membership; distinct from deleting or closing")
add("close", "Close", "actions", [L(5, 5, 19, 19), L(19, 5, 5, 19)], ["window-close"], "Close a surface; does not imply canceling underlying work")
add("check", "Choose or accept", "actions", [P("M4 12L9.5 17.5L20 6.5")], ["object-select", "dialog-ok", "dialog-ok-apply"])
add("refresh", "Refresh", "actions", [P("M4 9A8 8 0 0 1 17 5L20 8M20 4V8H16", "accent"), P("M20 15A8 8 0 0 1 7 19L4 16M4 20V16H8")],
    ["view-refresh"], "Read/reconcile current information; not blindly retry a command")
add("undo", "Undo", "actions", [P("M8 5L3 10L8 15", "accent"), P("M3 10H14A6 6 0 0 1 14 22")], ["edit-undo"], "Only show when the specific action supports undo")
add("redo", "Redo", "actions", [P("M16 5L21 10L16 15", "accent"), P("M21 10H10A6 6 0 0 0 10 22")], ["edit-redo"])
add("copy", "Copy", "actions", [P("M9 3H20V16", "accent"), R(4, 7, 12, 14, 1.5)], ["edit-copy"], "Copy content or recipe; a new operation keeps explicit new scope")
add("move", "Move", "actions", [P("M12 3V21M3 12H21"), P("M9 6L12 3L15 6M9 18L12 21L15 18M6 9L3 12L6 15M18 9L21 12L18 15", "accent")], ["transform-move", "edit-move"])
add("save", "Save", "actions", [P("M4 3H17L21 7V20Q21 21 20 21H4Q3 21 3 20V4Q3 3 4 3Z", "body"), P("M7 3V9H16V3", "accent"), R(7, 14, 10, 7, 1, "line")], ["document-save"])
add("open", "Open", "actions", [P("M10 4H4V20H20V14", "body"), P("M12 3H21V12M21 3L10 14", "accent")], ["document-open"])
add("edit", "Edit", "actions", [P("M4 16L15 5L19 9L8 20L3 21Z", "body"), P("M14.5 5.5L17 3L21 7L18.5 9.5", "accent"), L(4, 16, 8, 20)], ["document-edit", "edit"])
add("settings", "Settings", "actions", gear(), ["preferences-system", "emblem-system"])
add("power", "Power", "actions", [P("M6 6A9 9 0 1 0 18 6"), L(12, 2.8, 12, 12, "accent")], ["system-shutdown"], "Power action; label must identify its actual consequence")
add("lock", "Lock", "actions", [P("M7 10V7A5 5 0 0 1 17 7V10", "accent"), R(4, 10, 16, 11, 2), L(12, 14, 12, 17)], ["changes-prevent", "system-lock-screen"])
add("unlock", "Unlock", "actions", [P("M7 10V7A5 5 0 0 1 17 7", "accent"), R(4, 10, 16, 11, 2), L(12, 14, 12, 17)], ["changes-allow"])
add("fullscreen", "Fullscreen", "actions", [P("M9 3H3V9M15 3H21V9M3 15V21H9M15 21H21V15")], ["view-fullscreen"])
add("restore", "Restore view", "actions", [P("M9 3V9H3M15 3V9H21M3 15H9V21M15 21V15H21")], ["view-restore"], "Restore view geometry; not a promise of data rollback")
add("filter", "Filter", "actions", [P("M3 4H21L14 12V19L10 21V12Z", "body")], ["view-filter"])
add("sort", "Sort", "actions", [P("M5 4V20M2.5 17L5 20L7.5 17", "accent"), L(11, 5, 15, 5), L(11, 12, 18, 12), L(11, 19, 21, 19)], ["view-sort-ascending"], "Order controls require explicit key/direction labels")

# Places and files. Folder subtype badges are deliberately sparse at 16px.
add("folder", "Folder", "places", folder(), ["folder", "inode-directory"])
add("folder-open", "Open folder", "places", [P("M3 10V5H9L11 7H19V11", "body"), P("M3 12H21L18.5 20H3Z", "body"), L(5, 14, 18, 14, "accent")], ["folder-open"])
add("folder-music", "Music folder", "places", folder([P("M12 17V12L17 11V16", "accent"), E(10.5, 17.5, 1.5, 1, "solid"), E(15.5, 16.5, 1.5, 1, "solid")]), ["folder-music"])
add("folder-downloads", "Downloads folder", "places", folder([P("M12 11V17M9 14L12 17L15 14", "accent")]), ["folder-download", "folder-downloads"])
add("folder-documents", "Documents folder", "places", folder([P("M9 12H14L16 14V18H9Z", "line"), P("M14 12V14H16", "accent")]), ["folder-documents"])
add("folder-pictures", "Pictures folder", "places", folder([P("M8 18L11 14L13.5 17L16 14L18 18", "line"), C(9, 12.2, .8, "accent-solid")]), ["folder-pictures"])
add("folder-video", "Videos folder", "places", folder([P("M10 12L16 15L10 18Z", "accent-solid")]), ["folder-videos"])
add("folder-projects", "Projects folder", "places", folder([P("M9 12L6 15L9 18M15 12L18 15L15 18", "accent")]), ["folder-development"])
add("archive", "Archive", "mimetypes", [R(3, 4, 18, 5, 1), P("M5 9V20H19V9", "body"), R(9, 12, 6, 3, 0, "accent")], ["application-x-archive", "application-zip"])
add("trash", "Trash", "places", [P("M4 6H20M8 6V3H16V6", "accent"), P("M6 6L7 21H17L18 6", "body"), L(10, 10, 10, 17), L(14, 10, 14, 17)], ["user-trash", "edit-delete"], "Destructive delete/trash is not the close action")
add("document", "Document", "mimetypes", document(), ["text-x-generic", "application-pdf", "unknown"])
add("document-text", "Text document", "mimetypes", document([L(8, 12, 15, 12), L(8, 16, 15, 16)]), ["text-plain", "text-x-readme", "x-office-document"])
add("document-code", "Code document", "mimetypes", document([P("M9 12L6.5 15L9 18M14 12L16.5 15L14 18", "accent")]), ["text-x-script", "text-x-python", "text-html"])
add("document-audio", "Audio document", "mimetypes", document([P("M12.5 18V11L16 10.5", "accent"), E(10.5, 18, 2, 1.2, "solid")]), ["audio-x-generic"])
add("document-image", "Image document", "mimetypes", document([P("M7 18L10 13L13 17L15 14L17 18"), C(8, 10, .8, "accent-solid")]), ["image-x-generic"])
add("document-video", "Video document", "mimetypes", document([P("M9 11L16 15L9 19Z", "accent-solid")]), ["video-x-generic"])
add("document-table", "Spreadsheet", "mimetypes", document([R(7, 11, 9, 7, 0, "line"), L(10.5, 11, 10.5, 18, "accent"), L(7, 14.5, 16, 14.5)]), ["x-office-spreadsheet"])
add("package", "Package", "mimetypes", [P("M3 7L12 3L21 7V17L12 21L3 17Z", "body"), P("M3 7L12 11L21 7M12 11V21", "accent"), P("M7 5L16 9V13")], ["package-x-generic"])

# Devices: these are noun/capability pictures, never fabricated live meters.
add("computer", "Computer", "devices", [R(2.5, 5, 13, 11, 1.5), P("M9 16V20M5 20H13", "accent"), R(18, 3, 3.5, 18, 1), L(19.75, 7, 19.75, 8)], ["computer", "computer-desktop"])
add("display", "Display", "devices", [R(3, 4, 18, 13, 1.5), P("M12 17V21M8 21H16", "accent")], ["video-display", "preferences-desktop-display"])
add("laptop", "Laptop", "devices", [R(5, 3, 14, 13, 1.5), P("M5 16L2 20Q2 21 4 21H20Q22 21 22 20L19 16Z", "body"), L(10, 18.5, 14, 18.5, "accent")], ["computer-laptop"])
add("keyboard", "Keyboard", "devices", [R(2.5, 5, 19, 14, 2), P("M6 9H7M11 9H12M16 9H17M6 13H7M11 13H12M16 13H17", "line"), L(7, 16, 17, 16, "accent")], ["input-keyboard"])
add("mouse", "Mouse", "devices", [P("M6 9A6 6 0 0 1 18 9V15A6 6 0 0 1 6 15Z", "body"), L(12, 3, 12, 10, "accent")], ["input-mouse"])
add("headphones", "Headphones", "devices", [P("M4 14V11A8 8 0 0 1 20 11V14", "accent"), R(3, 12, 5, 8, 2), R(16, 12, 5, 8, 2)], ["audio-headphones"])
add("microphone", "Microphone", "devices", [R(8, 3, 8, 12, 4), P("M5 11V12A7 7 0 0 0 19 12V11", "accent"), P("M12 19V22M8 22H16")], ["audio-input-microphone"])
add("speaker", "Speaker", "devices", [R(5, 3, 14, 18, 2), C(12, 14.5, 3.5, "line"), C(12, 7, 1, "accent-solid")], ["audio-speakers"], "Output device identity, not its current volume level")
add("camera", "Camera", "devices", [P("M3 7H7L9 4H15L17 7H21V20H3Z", "body"), C(12, 13.5, 4, "line"), L(18.2, 10, 18.7, 10, "accent")], ["camera-photo", "camera-web"])
add("storage", "Storage", "devices", [P("M5 4H19L21 15V20H3V15Z", "body"), L(3, 15, 21, 15, "accent"), L(7, 18, 10, 18), C(17.5, 18, .8, "accent-solid")], ["drive-harddisk", "drive-harddisk-system"])
add("usb", "USB", "devices", [P("M12 19V3M12 11L6 8V5M12 14L18 11V8"), P("M9.5 5.5L12 3L14.5 5.5", "accent"), C(6, 4, 1.2, "accent-solid"), R(16.5, 5, 3, 3, 0, "accent-solid"), C(12, 20, 1.5, "solid")], ["drive-removable-media", "usb"])
add("battery", "Battery", "devices", [R(5, 4, 14, 17, 2), L(9, 2.5, 15, 2.5, "accent"), P("M9 9H15M12 6V12M9 16H15")], ["battery"], "Battery capability/polarity; not a charge percentage or charging report")
add("printer", "Printer", "devices", [P("M7 9V3H17V9", "body"), R(3, 9, 18, 9, 2), P("M7 14H17V21H7Z", "body"), L(10, 17.5, 14, 17.5, "accent")], ["printer"])
add("gamepad", "Game controller", "devices", [P("M7 6H17Q19 6 20 10L22 17Q22 21 18 19L15 16H9L6 19Q2 21 2 17L4 10Q5 6 7 6Z", "body"), P("M6 11H10M8 9V13"), C(16, 10, .9, "accent-solid"), C(18, 12.5, .9, "solid")], ["input-gaming"])

# Application categories remain generic and do not redraw third-party brands.
add("development", "Development", "categories", [P("M8 6L2 12L8 18M16 6L22 12L16 18"), L(14, 3.5, 10, 20.5, "accent")], ["applications-development"])
add("games", "Games", "categories", [P("M7 14H17L21 20H3Z", "body"), L(12, 14, 12, 8, "accent"), C(12, 5.5, 2.5, "body"), C(17.5, 17.5, .8, "accent-solid")], ["applications-games"])
add("graphics", "Graphics", "categories", [P("M12 3L21 14L15 21H9L3 14Z", "body"), P("M12 3V11M9 21L12 15L15 21", "accent"), C(12, 12.5, 1.5, "line")], ["applications-graphics"])
add("network", "Network", "categories", [C(12, 12, 9, "body"), E(12, 12, 4, 9), L(3, 12, 21, 12, "accent")], ["applications-internet", "network-workgroup"], "Network/Internet category, not a connection-health reading")
add("media", "Media", "categories", [R(3, 4, 18, 16, 1), L(7, 4, 7, 20, "accent"), L(17, 4, 17, 20, "accent"), P("M3 9H7M3 15H7M17 9H21M17 15H21"), P("M10 9L15 12L10 15Z", "solid")], ["applications-multimedia"])
add("office", "Office", "categories", [P("M8 7V3H16V7", "accent"), R(3, 7, 18, 14, 2), P("M3 12Q12 17 21 12"), L(12, 12, 12, 15, "accent")], ["applications-office"])
add("system", "System", "categories", [R(6, 6, 12, 12, 2), P("M9 3V6M15 3V6M9 18V21M15 18V21M3 9H6M3 15H6M18 9H21M18 15H21", "accent"), R(9, 9, 6, 6, 1, "line")], ["applications-system", "cpu"])
add("utilities", "Utilities", "categories", [P("M14 3A6 6 0 0 0 7 10L3 18L6 21L14 14A6 6 0 0 0 21 7L17 11L13 7Z", "body")], ["applications-utilities", "applications-other"])
add("music", "Music", "categories", [P("M9 17V5L20 3V15", "accent"), E(6.5, 17.5, 2.5, 2, "body"), E(17.5, 15.5, 2.5, 2, "body"), L(9, 9, 20, 7)], ["applications-audio"], "Music category; actual notation, not a decorative signal waveform")

# Existing shell utility identities.
add("calculator", "Calculator", "apps", [R(4, 2.5, 16, 19, 2), R(7, 5.5, 10, 4, 0, "accent"), P("M7 13H9M15 13H17M7 17H9M15 17H17"), L(8, 12, 8, 14)], ["accessories-calculator", "io.aether.calc-menu"])
add("audio-console", "Audio console", "apps", [P("M5 3V8M5 13V21M12 3V13M12 18V21M19 3V6M19 11V21", "line"), R(2.5, 8, 5, 5, 1, "body"), R(9.5, 13, 5, 5, 1, "body"), R(16.5, 6, 5, 5, 1, "body")], ["multimedia-volume-control", "audio-card", "io.aether.audio-menu"])
add("wifi", "Wireless network", "devices", [P("M3 8A14 14 0 0 1 21 8M6 12A9 9 0 0 1 18 12M9 16A4 4 0 0 1 15 16"), C(12, 20, 1, "accent-solid")], ["network-wireless", "io.aether.wifi-menu"], "Wireless capability; never override signal-strength or security-specific status names")
add("bluetooth", "Bluetooth", "devices", [P("M12 2L18 7L6 17L12 22V2M6 7L18 17L12 22", "accent")], ["bluetooth", "preferences-system-bluetooth", "io.aether.bt-menu"], "Conventional protocol sign; not an app logo or a claimed universal pictogram")
add("cast", "Cast display", "apps", [P("M3 8V4H21V20H16", "body"), P("M3 12A9 9 0 0 1 12 21M3 16A5 5 0 0 1 8 21", "accent"), C(3, 21, .8, "solid")], ["video-television", "io.aether.cast-menu"])
add("remote", "Remote desktop", "apps", [R(2.5, 3.5, 12, 10, 1.5), R(9.5, 10.5, 12, 10, 1.5), P("M7 10L12 15M8.5 15H12V11.5", "accent")], ["preferences-desktop-remote-desktop", "io.aether.remote-menu"], "Two named endpoints still require labels; icon does not identify direction alone")
add("keybinds", "Keyboard shortcuts", "apps", [R(3, 4, 8, 8, 1.5), R(13, 12, 8, 8, 1.5), P("M7 7V9M6 8H8M16 15H18V17M18 15L15.5 17.5", "accent"), P("M14 4H20V9", "line")], ["preferences-desktop-keyboard-shortcuts", "io.aether.keybind-guide"])

# State vocabulary: shape plus label, never color alone or fabricated evidence.
add("info", "Information", "status", [P("M4 4H20V16H10L5 21V16H4Z", "body"), L(8, 8, 16, 8), L(8, 12, 13, 12, "accent")], ["dialog-information"], "Information/callout; no letter-only mark")
add("warning", "Warning", "status", [P("M12 3L22 21H2Z", "body"), L(12, 9, 12, 14), C(12, 17.5, .9, "solid")], ["dialog-warning"], state="warning")
add("error", "Error", "status", [P("M8 3H16L21 8V16L16 21H8L3 16V8Z", "body"), P("M8 8L16 16M16 8L8 16")], ["dialog-error"], state="danger")
add("success", "Supported success", "status", [C(12, 12, 9, "body"), P("M7 12L10.5 15.5L17 8.5")], ["emblem-ok", "emblem-default"], "Use only when evidence supports the stated success", state="success")
add("pending", "Pending", "status", [C(12, 12, 8.5, "body"), P("M12 6V12L16 14", "accent")], ["appointment-soon", "content-loading"], "Static pending mark; no guarantee of a queued or cancelable operation")
add("offline", "Offline or disconnected", "status", [P("M10 6L11 5A5 5 0 0 1 19 11L18 12M14 18L13 19A5 5 0 0 1 5 13L6 12", "outline"), P("M3 3L21 21", "accent")], ["network-offline"], "Disconnected ends, distinct from a failed command", state="secondary")
add("connected", "Connected", "status", [P("M10 7L12 5A5 5 0 0 1 19 12L17 14M14 17L12 19A5 5 0 0 1 5 12L7 10", "outline"), L(8.5, 15.5, 15.5, 8.5, "accent")], ["network-connect", "emblem-shared"], "A connection observation, not proof of physical output", state="success")


def attr_string(attrs):
    return " ".join(f'{key}="{str(value).replace(chr(34), "&quot;")}"' for key, value in attrs.items())


def element(shape, *, stroke, fill, width=2, fixed_stroke=False):
    # GTK3's symbolic recolor path does not recolor opaque line-element cores.
    # Equivalent path segments retain native currentColor consistently.
    tag, geometry = shape.tag, dict(shape.attrs)
    if tag == "line":
        tag = "path"
        geometry = {"d": f'M{geometry["x1"]} {geometry["y1"]}L{geometry["x2"]} {geometry["y2"]}'}
    attrs = {**geometry, "fill": fill, "stroke": stroke,
             "stroke-width": width, "stroke-linecap": "round", "stroke-linejoin": "round"}
    if fixed_stroke:
        attrs["vector-effect"] = "non-scaling-stroke"
    return f"<{tag} {attr_string(attrs)}/>"


def mix_hex(first, second, amount):
    return "#" + "".join(f"{round(int(first[i:i+2],16)*(1-amount)+int(second[i:i+2],16)*amount):02x}" for i in (1,3,5))


def svg(icon, palette, variant, size=None):
    symbolic = variant == "symbolic"
    object_icon = any(shape.role == "body" for shape in icon["shapes"])
    stroke_width = {16: 2.1, 24: 1.8, 32: 1.5, 48: 1.15}.get(size, .65 if object_icon else 1.8)
    prefix = icon["id"] + "-" + variant + (f"-{size}" if size else "-scalable")
    edge_id, body_id = prefix + "-edge", prefix + "-body"
    if symbolic:
        definitions = ""
        outline = ink = accent = "currentColor"
        body = "none"
    else:
        outline = f"url(#{edge_id})"
        ink, accent = palette["text"], palette["accent"]
        if icon["state"]:
            outline = palette[icon["state"]]
            accent = outline
        body = f"url(#{body_id})"
        definitions = (f'<defs><linearGradient id="{edge_id}" x1="0" y1="0" x2="1" y2="1">'
                       f'<stop stop-color="{palette["selection"]}"/><stop offset="1" stop-color="{palette["accent"]}"/>'
                       f'</linearGradient><linearGradient id="{body_id}" x1="0" y1="0" x2="0.8" y2="1">'
                       f'<stop stop-color="{mix_hex(palette["raised"], palette["selection"], .30)}"/><stop offset="1" stop-color="{palette["surface"]}"/>'
                       '</linearGradient></defs>')
    shapes = []
    for shape in icon["shapes"]:
        solid = shape.role in ("solid", "accent-solid")
        color = accent if shape.role in ("accent", "accent-solid") else outline if shape.role in ("body", "outline") else ink
        if symbolic:
            shapes.append(element(shape, stroke="none" if solid else "currentColor",
                                  fill="currentColor" if solid else "none"))
        else:
            # A bounded dark/bright ink keyline protects unfilled glyphs when
            # composited on another background; no expensive glow filters.
            if not solid and (shape.role == "body" or not object_icon):
                shapes.append(element(shape, stroke=palette["canvas"], fill=body if shape.role == "body" else "none", width=stroke_width*1.8))
            shapes.append(element(shape, stroke="none" if solid else color,
                                  fill=color if solid else body if shape.role == "body" else "none", width=stroke_width))
            if shape.role == "body" and (size is None or size >= 48):
                shine = Shape(shape.tag, {**shape.attrs, "opacity": .32}, shape.role)
                shapes.append(element(shine, stroke=ink, fill="none", width=stroke_width*.30))
    title = icon["label"].replace("&", "&amp;")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size or 24}" height="{size or 24}" viewBox="0 0 24 24" role="img" aria-labelledby="{prefix}-title">'
            f'<title id="{prefix}-title">{title}</title>{definitions}' + "".join(shapes) + '</svg>\n')


def generate(output, tokens, outline_helper):
    output.mkdir(parents=True, exist_ok=True)
    registry = []
    aliases = {}
    hashes = {}
    for icon in ICONS:
        record = {k: v for k, v in icon.items() if k != "shapes"}
        record["files"] = {}
        record["sized_files"] = {}
        for variant, palette in [("color-dark", tokens["color"]), ("color-light", tokens["icon_light"]), ("symbolic", tokens["color"])]:
            filename = icon["id"] + ("-symbolic" if variant == "symbolic" else "") + ".svg"
            relative = Path(variant) / icon["context"] / filename
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            text = svg(icon, palette, variant)
            ET.fromstring(text)
            destination.write_text(text)
            record["files"][variant] = str(relative)
            hashes[str(relative)] = hashlib.sha256(text.encode()).hexdigest()
            if variant != "symbolic":
                record["sized_files"][variant] = {}
                for size in (16,24,32,48):
                    relative_size = Path(variant) / str(size) / icon["context"] / filename
                    destination_size = output / relative_size
                    destination_size.parent.mkdir(parents=True,exist_ok=True)
                    sized_text = svg(icon,palette,variant,size)
                    ET.fromstring(sized_text)
                    destination_size.write_text(sized_text)
                    record["sized_files"][variant][str(size)] = str(relative_size)
                    hashes[str(relative_size)] = hashlib.sha256(sized_text.encode()).hexdigest()
        for alias in icon["aliases"]:
            if alias in aliases:
                raise ValueError(f'Duplicate alias {alias}')
            aliases[alias] = icon["id"]
        registry.append(record)
    # GTK's native symbolic recolor requires genuine filled contours. Capture
    # the authored SVG geometry through Qt and outline strokes analytically;
    # runtime files contain only currentColor filled paths, not raster tracing.
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    symbolic_files = [output / record["files"]["symbolic"] for record in registry]
    result = subprocess.run([str(outline_helper), *map(str, symbolic_files)], env=environment,
                            capture_output=True, text=True, check=True, timeout=30)
    for relative in hashes:
        data = (output/relative).read_bytes()
        ET.fromstring(data)
        hashes[relative] = hashlib.sha256(data).hexdigest()
    payload = {"family": "Instrument/Score Aether", "version": "0.1.0", "theme_id": "aether-score",
               "view_box": [0, 0, 24, 24], "symbolic_stroke_units": 2,
               "full_color_optical_stroke_units": {"16":2.1,"24":1.8,"32":1.5,"48":1.15,"scalable_object":.65,"scalable_action":1.8},
               "symbolic_construction":"Native Qt vector stroke outlines, currentColor fills; no raster tracing.",
               "outline_tool_result":result.stdout.strip(),
               "license":"MIT", "provenance":"Original project-authored paths; no upstream paths or app logos imported.",
               "icons": registry, "aliases": aliases,
               "notes": ["Symbolic variants append -symbolic to primary IDs and aliases.",
                         "Only generic noun/action/protocol signs; no branded app logos.",
                         "Quantitative battery/signal/volume and evidence-specific states require live adapters."]}
    (output / "registry.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    (output / "files.sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    print(f'Generated {len(registry)} icon identities, {len(aliases)} aliases, {len(hashes)} SVG files at {output}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "generated")
    parser.add_argument("--palette", type=Path, default=HERE / "palette.json")
    parser.add_argument("--outline-helper", type=Path, help="Optional prebuilt native vector-outline helper")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="aether-icon-outline-build-") as temporary:
        helper = args.outline_helper
        if helper is None:
            helper = Path(temporary) / "outline-symbolic"
            flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Svg", "Qt6Gui"],text=True))
            subprocess.run(["g++", "-fPIC", str(HERE/"outline-symbolic.cpp"), "-o", str(helper), *flags],check=True)
        generate(args.output, json.loads(args.palette.read_text()), helper)


if __name__ == "__main__":
    main()
