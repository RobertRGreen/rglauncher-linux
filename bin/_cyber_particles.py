#!/usr/bin/env python3
"""Bounded Cairo signal dust behind GTK card content; no display needed to import.

API: ParticleField(count=PARTICLE_COUNT, seed=7).advance(seconds)/draw(cr,w,h)
works with cairo.ImageSurface. ParticleLayer(content) is a Gtk.DrawingArea.
install_particles(container_widget) -> ParticleLayer preserves a Gtk.Box card's
style, allocation, margins, children and packing, and puts dust BELOW its content.
Call once after constructing initial children and before show_all().

34ms => <=29.42 redraw requests/s. Default 32, hard cap 48 particles, at most
96 tiny primitives/frame (~2824/s). One reusable ARGB32 buffer <=1280x800
(~3.91 MiB) per surface; no trails, expanding histories, threads or blur kernels.
At the buffer cap, clear+composite is ~60M pixel passes/s per visible surface;
this is a bound on work, NOT a measured CPU percentage. Hidden/destroyed widgets
stop their timer. gtk-enable-animations=false freezes motion. Live GTK/compositor
cost (especially the pre-existing CSS glows and carousel tick) needs measurement.
"""
import math
import random
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from _cyber_theme import ACCENT, ACCENT2, PURPLE, rgb_channels

PARTICLE_COUNT = 32
MAX_PARTICLES = 48
FRAME_INTERVAL_MS = 34
FIELD_ALPHA = 0.10  # Applied ONCE to the combined field, including overlaps/flicker.
MAX_BUFFER_WIDTH = 1280
MAX_BUFFER_HEIGHT = 800
PARTICLE_COLORS = (ACCENT, ACCENT2, PURPLE)


class ParticleField:
    """Deterministic normalized drift; draw is independent of GTK and wall time."""

    def __init__(self, count=PARTICLE_COUNT, seed=7):
        rng = random.Random(seed)
        self.particles = [
            [rng.random(), rng.random(), rng.uniform(-0.009, 0.009),
             rng.uniform(-0.018, -0.006), rng.uniform(1.0, 2.0),
             i % len(PARTICLE_COLORS), rng.random() * 9, i % 5 == 0]
            for i in range(max(0, min(MAX_PARTICLES, int(count))))
        ]
        self.elapsed = 0.0
        self._surface = None

    def advance(self, seconds):
        # No catch-up bursts or jumps after a stalled main loop.
        dt = max(0.0, min(0.1, seconds))
        self.elapsed += dt
        for p in self.particles:
            p[0] = (p[0] + p[2] * dt) % 1.0
            p[1] = (p[1] + p[3] * dt) % 1.0

    def draw(self, cr, width, height):
        """Paint transparent dust into cr; aggregate opacity never exceeds 0.10.

        A bounded reusable buffer is composited once, so stacked particles never
        add their alphas beyond FIELD_ALPHA. Glitch only dims, never brightens.
        """
        if width <= 0 or height <= 0:
            return
        scale = min(1.0, MAX_BUFFER_WIDTH / width, MAX_BUFFER_HEIGHT / height)
        bw, bh = max(1, math.ceil(width * scale)), max(1, math.ceil(height * scale))
        if (self._surface is None or self._surface.get_width() != bw
                or self._surface.get_height() != bh):
            self._surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, bw, bh)
        dust = cairo.Context(self._surface)
        dust.set_operator(cairo.OPERATOR_CLEAR)
        dust.paint()
        dust.set_operator(cairo.OPERATOR_OVER)
        dust.scale(bw / width, bh / height)
        for x, y, _vx, _vy, radius, color, phase, glyph in self.particles:
            # Independent 70ms dropout every ~9s gives sparse digital flicker.
            a = 0.18 if (self.elapsed + phase) % 9 < 0.07 else 0.75
            dust.set_source_rgba(*(c / 255 for c in rgb_channels(PARTICLE_COLORS[color])), a)
            px, py = x * width, y * height
            if glyph:
                # Tiny terminal cross / broken register, independent of font lookup.
                dust.set_line_width(1)
                dust.move_to(px - 3, py)
                dust.line_to(px + 3, py)
                dust.move_to(px, py - 2)
                dust.line_to(px, py + 2)
                dust.stroke()
            else:
                dust.arc(px, py, radius, 0, math.tau)
                dust.fill()
        cr.save()
        cr.scale(width / bw, height / bh)
        cr.set_source_surface(self._surface, 0, 0)
        cr.paint_with_alpha(FIELD_ALPHA)
        cr.restore()


class ParticleLayer(Gtk.DrawingArea):
    """Windowless, noninteractive layer sized by its overlaid content box."""

    def __init__(self, content):
        super().__init__()
        self.content = content
        self.field = ParticleField()
        self._timer = None
        self._last_time = None
        self.set_has_window(False)
        self.set_can_focus(False)
        self.connect("draw", self._draw)
        self.connect("map", self._sync_motion)
        self.connect("unmap", self._stop)
        self.connect("destroy", self._destroy)
        self._settings = self.get_settings()
        self._settings_handler = self._settings.connect(
            "notify::gtk-enable-animations", self._sync_motion) if self._settings else None

    # Gtk.Overlay normally ignores overlay children's size requests. Delegate
    # all requests to the content so variable-height menus retain their layout.
    def do_get_request_mode(self):
        return self.content.get_request_mode()

    def do_get_preferred_width(self):
        return self.content.get_preferred_width()

    def do_get_preferred_height(self):
        return self.content.get_preferred_height()

    def do_get_preferred_height_for_width(self, width):
        return self.content.get_preferred_height_for_width(width)

    def do_get_preferred_width_for_height(self, height):
        return self.content.get_preferred_width_for_height(height)

    def _sync_motion(self, *_args):
        enabled = not self._settings or self._settings.get_property("gtk-enable-animations")
        if self.get_mapped() and enabled and self._timer is None:
            self._last_time = time.monotonic()
            self._timer = GLib.timeout_add(FRAME_INTERVAL_MS, self._tick)
        elif not self.get_mapped() or not enabled:
            self._stop()

    def _stop(self, *_args):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        self._last_time = None

    def _destroy(self, *_args):
        self._stop()
        if self._settings_handler is not None:
            self._settings.disconnect(self._settings_handler)
            self._settings_handler = None
        self.field._surface = None

    def _tick(self):
        now = time.monotonic()
        self.field.advance(now - self._last_time)
        self._last_time = now
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _draw(self, _widget, cr):
        self.field.draw(cr, self.get_allocated_width(), self.get_allocated_height())
        return False


def install_particles(container_widget):
    """Wrap a fully built Gtk.Box's children, returning its ParticleLayer.

    The styled card stays outside: CSS raster/gradient -> DrawingArea dust ->
    original full-opacity controls. Existing child references remain valid.
    The drawing area has no input window; foreground events retain their paths.
    Repeated installation returns the existing layer without reparenting again.
    """
    from _cyber_theme import INSTRUMENT_SCORE
    if INSTRUMENT_SCORE:
        from _aether_surfaces import install_surface
        return install_surface(container_widget)
    existing = getattr(container_widget, "_cyber_particle_layer", None)
    if existing is not None:
        return existing
    content = Gtk.Box(orientation=container_widget.get_orientation(),
                      spacing=container_widget.get_spacing())
    content.set_homogeneous(container_widget.get_homogeneous())
    content.set_baseline_position(container_widget.get_baseline_position())
    for child in list(container_widget.get_children()):
        expand, fill, padding, pack_type = container_widget.query_child_packing(child)
        container_widget.remove(child)
        if pack_type == Gtk.PackType.END:
            content.pack_end(child, expand, fill, padding)
        else:
            content.pack_start(child, expand, fill, padding)
    overlay = Gtk.Overlay()
    layer = ParticleLayer(content)
    overlay.add(layer)
    overlay.add_overlay(content)
    content.set_halign(Gtk.Align.FILL)
    content.set_valign(Gtk.Align.FILL)
    container_widget.pack_start(overlay, True, True, 0)
    container_widget._cyber_particle_layer = layer
    return layer
