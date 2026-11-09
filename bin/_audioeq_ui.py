"""GTK equalizer editor with real monitor FFT and scrolling spectrogram."""
import math
import os
import subprocess
import numpy as np
import cairo
from gi.repository import Gtk, GLib, Pango
import _audioeq as eq


def text(value, cls='am-meta'):
    w = Gtk.Label(label=value)
    w.get_style_context().add_class(cls)
    w.set_xalign(0)
    w.set_ellipsize(Pango.EllipsizeMode.END)
    return w


def button(value, callback):
    w = Gtk.Button(label=value)
    w.get_style_context().add_class('am-pill')
    w.connect('clicked', callback)
    return w


def freq_label(f):
    return f'{f / 1000:.1f}k' if f >= 1000 else f'{f:.0f}'


def response(s, freqs, rate=48000):
    """Same RBJ peaking biquads as PipeWire, including preamp."""
    if s.get('bypass') or not s.get('enabled'):
        return np.zeros_like(freqs)
    z = np.exp(-2j * np.pi * freqs / rate)
    out = np.full(len(freqs), eq.effective_preamp(s))
    for f, gain in zip(eq.frequencies(s['bands']), s['gains']):
        a = 10 ** (gain / 40)
        w = 2 * np.pi * f / rate
        alpha = np.sin(w) / (2 * eq.q_value(s['bands']))
        cs = np.cos(w)
        num = (1 + alpha * a) - 2 * cs * z + (1 - alpha * a) * z * z
        den = (1 + alpha / a) - 2 * cs * z + (1 - alpha / a) * z * z
        out += 20 * np.log10(np.maximum(np.abs(num / den), 1e-10))
    return out


class EQPanel(Gtk.Box):
    def __init__(self, kind, name, desc, back):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.kind, self.name = kind, name
        self.s = eq.settings(kind, name)
        self.proc = None
        self.target = None
        self.pending = b''
        self.samples = np.zeros(4096, dtype=np.float32)
        self.level = np.full(256, -90.)
        self.peaks = self.level.copy()
        self.history = np.zeros((110, 256), dtype=np.uint32)
        self.alive = True
        self.last_audio = GLib.get_monotonic_time()
        top = Gtk.Box(spacing=16)
        top.pack_start(button('‹ BACK', lambda *_: back()), False, False, 0)
        top.pack_start(text('DEVICE EQ  //  ' + desc, 'am-section'), True, True, 0)
        self.pack_start(top, False, False, 0)
        controls = Gtk.Box(spacing=14)
        self.enable = Gtk.CheckButton(label='ENABLE EQ')
        self.enable.set_active(self.s['enabled'])
        self.enable.connect('toggled', self._enable)
        controls.pack_start(self.enable, False, False, 0)
        bypass = Gtk.CheckButton(label='BYPASS')
        bypass.set_active(self.s.get('bypass', False))
        bypass.connect('toggled', lambda w: self._set('bypass', w.get_active()))
        controls.pack_start(bypass, False, False, 0)
        controls.pack_start(text('BANDS'), False, False, 0)
        count = Gtk.SpinButton.new_with_range(4, 24, 1)
        count.set_value(self.s['bands'])
        count.connect('value-changed', self._count)
        controls.pack_start(count, False, False, 0)
        controls.pack_start(text('PREAMP'), False, False, 0)
        self.preamp = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -24, 6, .5)
        self.preamp.set_size_request(220, -1)
        self.preamp.set_digits(1)
        self.preamp.set_value(self.s.get('preamp', 0.))
        self.preamp.add_mark(0, Gtk.PositionType.BOTTOM, '0 dB')
        self.preamp.connect('value-changed', lambda w: self._set('preamp', w.get_value()))
        controls.pack_start(self.preamp, False, False, 0)
        headroom = Gtk.CheckButton(label='AUTO HEADROOM')
        self.headroom = headroom
        headroom.set_active(self.s.get('auto_headroom', True))
        headroom.set_tooltip_text('Scale automatic gain reduction with the amount slider. 100% compensates for boosts with 3 dB extra headroom.')
        headroom.connect('toggled', lambda w: (
            self._set('auto_headroom', w.get_active()),
            self.headroom_amount.set_sensitive(w.get_active())))
        controls.pack_start(headroom, False, False, 0)
        self.headroom_amount = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.headroom_amount.set_size_request(160, -1)
        self.headroom_amount.set_digits(0)
        self.headroom_amount.set_value_pos(Gtk.PositionType.RIGHT)
        self.headroom_amount.connect('format-value', lambda w, v: f'{v:.0f}%')
        self.headroom_amount.set_value(self.s.get('headroom_amount', 100.))
        self.headroom_amount.set_sensitive(headroom.get_active())
        self.headroom_amount.set_tooltip_text('Headroom amount: 0% = no automatic reduction; 50% = half the reduction in dB; 100% = full reduction.')
        self.headroom_amount.connect('value-changed', lambda w: self._set('headroom_amount', w.get_value()))
        controls.pack_start(self.headroom_amount, False, False, 0)
        controls.pack_end(button('FLAT / RESET', self._reset), False, False, 0)
        self.pack_start(controls, False, False, 0)
        presets = Gtk.Box(spacing=12)
        presets.pack_start(text('PRESET'), False, False, 0)
        self.preset = Gtk.ComboBoxText()
        self.preset.append('Custom', 'Custom / manual')
        for preset_name in eq.PRESETS:
            self.preset.append(preset_name, preset_name)
        self.preset.set_active_id(self.s.get('preset', 'Custom'))
        self.preset.connect('changed', self._preset)
        presets.pack_start(self.preset, False, False, 0)
        presets.pack_start(text('Preserves band count · auto headroom compensates for EQ boosts'), True, True, 0)
        staged = Gtk.Button(label='SMART CALIBRATION · STAGED')
        staged.get_style_context().add_class('am-pill')
        staged.set_sensitive(False)
        staged.set_tooltip_text('Planned: compare band loudness one at a time. No calibration tones or automatic EQ run yet.')
        presets.pack_end(staged, False, False, 0)
        self.pack_start(presets, False, False, 0)
        self.status = text('Ready · settings save automatically', 'am-status')
        self.pack_start(self.status, False, False, 0)
        self.overlay = Gtk.Overlay()
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(700, 430)
        self.canvas.connect('draw', self._draw)
        self.overlay.add(self.canvas)
        self.faders = Gtk.Box(spacing=0, homogeneous=True)
        self.faders.set_margin_start(48)
        self.faders.set_margin_end(24)
        self.faders.set_margin_top(35)
        self.faders.set_margin_bottom(34)
        self.overlay.add_overlay(self.faders)
        self.pack_start(self.overlay, True, True, 0)
        self.pack_start(text('31.5 Hz — 16 kHz  ·  ±18 dB  ·  spectrum / peak hold / waterfall: post-EQ  ·  double-click a fader to zero'), False, False, 0)
        self.pack_start(text('Auto headroom compensates for boosts. Fixed hardware / JACK / direct-monitor routes keep their own routing.'), False, False, 0)
        self._build_faders()
        provider = Gtk.CssProvider()
        provider.load_from_data(b'''
            scale.eq-fader trough { background: rgba(8,12,22,0.38); min-width: 5px; border: 1px solid rgba(120,140,180,0.16); }
            scale.eq-fader highlight { background: rgba(57,230,215,0.12); }
            scale.eq-fader slider { background: #101b2a; border: 2px solid #39e6d7; min-width: 22px; min-height: 8px; border-radius: 2px; }
            scale.eq-fader { padding: 0 8px; }
        ''')
        Gtk.StyleContext.add_provider_for_screen(self.get_screen(), provider, 650)
        self.connect('destroy', self._destroy)
        self.timer = GLib.timeout_add(33, self._tick)
        self.show_all()

    def _set(self, k, value):
        self.s[k] = value
        eq.save(self.kind, self.name, self.s)
        self.canvas.queue_draw()

    def _preset(self, w):
        name = w.get_active_id()
        if name not in eq.PRESETS:
            return
        self.s.update(gains=eq.preset_gains(name, self.s['bands']),
                      preamp=0., auto_headroom=True, preset=name)
        self.preamp.set_value(0.)
        self.headroom.set_active(True)
        eq.save(self.kind, self.name, self.s)
        self._build_faders()
        self.canvas.queue_draw()

    def _enable(self, w):
        self._set('enabled', w.get_active())

    def _count(self, w):
        n = w.get_value_as_int()
        oldf, newf = eq.frequencies(self.s['bands']), eq.frequencies(n)
        self.s['gains'] = np.interp(np.log(newf), np.log(oldf), self.s['gains']).tolist()
        self._set('bands', n)
        self._build_faders()

    def _gain(self, w, i, value):
        self.s['preset'] = 'Custom'
        self.preset.set_active_id('Custom')
        self.s['gains'][i] = round(w.get_value(), 1)
        value.set_text(f'{w.get_value():+.1f}')
        eq.save(self.kind, self.name, self.s)
        self.canvas.queue_draw()

    def _build_faders(self):
        for ch in self.faders.get_children():
            ch.destroy()
        self.scales = []
        for i, f in enumerate(eq.frequencies(self.s['bands'])):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            value = text(f'{self.s["gains"][i]:+.1f}', 'am-value')
            value.set_xalign(.5)
            col.pack_start(value, False, False, 0)
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, -18, 18, .1)
            sc.set_inverted(True)
            sc.set_draw_value(False)
            sc.set_value(self.s['gains'][i])
            sc.get_style_context().add_class('eq-fader')
            sc.set_tooltip_text(f'{f:.1f} Hz · double-click to reset')
            sc.connect('value-changed', self._gain, i, value)
            sc.connect('button-press-event', self._double_click)
            col.pack_start(sc, True, True, 0)
            hz = text(freq_label(f))
            hz.set_xalign(.5)
            col.pack_start(hz, False, False, 0)
            self.faders.pack_start(col, True, True, 0)
            self.scales.append(sc)
        self.faders.show_all()

    def _double_click(self, w, event):
        from gi.repository import Gdk
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            w.set_value(0)
            return True
        return False

    def _reset(self, *_):
        self.s['preset'] = 'Flat'
        self.preset.set_active_id('Flat')
        self.s['gains'] = [0.] * self.s['bands']
        self.s['preamp'] = 0.
        self.preamp.set_value(0)
        eq.save(self.kind, self.name, self.s)
        self._build_faders()

    def _capture(self):
        target = eq.live_map().get(eq.key(self.kind, self.name), self.name)
        if self.kind == 'sink':
            # Physical monitor includes every post-EQ stream and hardware volume.
            target = self.name + '.monitor'
        if target == self.target and self.proc and self.proc.poll() is None:
            return
        self._stop_capture()
        self.target = target
        self.proc = subprocess.Popen(['parec', '--device=' + target, '--raw', '--format=float32le',
                                      '--rate=48000', '--channels=1', '--latency-msec=30',
                                      '--property=application.name=AudioConsoleSpectrum',
                                      '--property=node.name=ac_eq_analyzer'],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        os.set_blocking(self.proc.stdout.fileno(), False)

    def _tick(self):
        if not self.alive:
            return False
        if not self.get_mapped():
            self._stop_capture()
            return True
        self._capture()
        data = bytearray(self.pending)
        try:
            while True:
                chunk = os.read(self.proc.stdout.fileno(), 65536)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 192000:
                    break
        except BlockingIOError:
            pass
        size = len(data) // 4 * 4
        self.pending = bytes(data[size:])
        if size:
            samples = np.frombuffer(data[:size], dtype='<f4')
            self.samples = np.concatenate((self.samples, samples))[-4096:]
            self.last_audio = GLib.get_monotonic_time()
        elif GLib.get_monotonic_time() - self.last_audio > 250000:
            self.samples *= .6
        fft = np.abs(np.fft.rfft(self.samples * np.hanning(4096))) / 1024
        freqs = np.fft.rfftfreq(4096, 1 / 48000)
        bins = np.geomspace(20, 20000, 256)
        db = np.interp(bins, freqs, 20 * np.log10(np.maximum(fft, 1e-6)))
        self.level = np.maximum(db, self.level - 1.5)
        self.peaks = np.maximum(self.level, self.peaks - .2)
        energy = np.clip((self.level + 85) / 75, 0, 1)
        r = (energy ** 2 * 230).astype(np.uint32)
        g = (energy * 210).astype(np.uint32)
        b = (energy * 190 + energy ** .5 * 35).astype(np.uint32)
        self.history[1:] = self.history[:-1]
        self.history[0] = (r << 16) | (g << 8) | b
        peak = 20 * math.log10(max(float(np.max(np.abs(self.samples))), 1e-6))
        state = 'OFF · monitoring' if not self.s['enabled'] else ('BYPASSED' if self.s.get('bypass') else 'EQ ACTIVE')
        if self.s['enabled'] and eq.key(self.kind, self.name) not in eq.live_map():
            state = 'CONNECTING / DEVICE UNAVAILABLE'
        self.status.set_text(f'{state}   ·   {self.s["bands"]} bands   ·   peak {peak:.1f} dBFS' +
                             (f'   ·   effective preamp {eq.effective_preamp(self.s):+.1f} dB' if self.s['enabled'] and not self.s.get('bypass') else '') +
                             ('   ·   CLIPPING — lower preamp' if peak > -.3 else ''))
        self.canvas.queue_draw()
        return True

    def _draw(self, w, cr):
        width, height = w.get_allocated_width(), w.get_allocated_height()
        left, right, top, bottom = 48, width - 24, 62, height - 62
        span = right - left
        cr.set_source_rgb(.025, .04, .065)
        cr.paint()
        surface = cairo.ImageSurface.create_for_data(self.history, cairo.FORMAT_RGB24, 256, 110)
        cr.save()
        cr.translate(left, top)
        cr.scale(span / 256, (bottom - top) / 110)
        cr.set_source_surface(surface)
        cr.paint_with_alpha(.48)
        cr.restore()
        def x(f):
            # Faders use evenly spaced log-frequency centers within each column.
            n = self.s['bands']
            return left + span * (.5 / n + math.log(f / 31.5) / math.log(16000 / 31.5) * (n - 1) / n)
        def y(db):
            return top + (18 - db) / 36 * (bottom - top)
        cr.set_font_size(11)
        for db in (-18, -12, -6, 0, 6, 12, 18):
            cr.set_source_rgba(.4, .55, .65, .5 if db == 0 else .18)
            cr.move_to(left, y(db))
            cr.line_to(right, y(db))
            cr.stroke()
            cr.move_to(5, y(db) + 4)
            cr.show_text(f'{db:+d}')
        for f in (63, 125, 250, 500, 1000, 2000, 4000, 8000):
            cr.set_source_rgba(.4, .55, .65, .15)
            cr.move_to(x(f), top)
            cr.line_to(x(f), bottom)
            cr.stroke()
        # Live filled spectrum and fading peak trace share the logarithmic axis.
        bins = np.geomspace(20, 20000, 256)
        cr.save()
        cr.rectangle(left, top, span, bottom - top)
        cr.clip()
        for levels, alpha in ((self.level, .85), (self.peaks, .3)):
            cr.new_path()
            for i, f in enumerate(bins):
                yy = bottom - np.clip((levels[i] + 90) / 90, 0, 1) * (bottom - top)
                (cr.move_to if i == 0 else cr.line_to)(x(f), yy)
            cr.set_source_rgba(.2, .8, .95, alpha)
            cr.set_line_width(1.4)
            cr.stroke_preserve()
            if alpha > .5:
                cr.line_to(x(bins[-1]), bottom)
                cr.line_to(x(bins[0]), bottom)
                cr.close_path()
                cr.set_source_rgba(.1, .6, .8, .13)
                cr.fill()
        frequencies = np.geomspace(20, 20000, 512)
        gains = response(self.s, frequencies)
        cr.new_path()
        for i, (f, db) in enumerate(zip(frequencies, gains)):
            (cr.move_to if i == 0 else cr.line_to)(x(f), y(db))
        cr.set_source_rgb(.9, .55, 1.)
        cr.set_line_width(2.6)
        cr.stroke()
        cr.restore()
        cr.set_source_rgba(.75, .65, .9, .8)
        cr.move_to(left, 20)
        cr.show_text('GAIN dB   /   LIVE SPECTRUM + WATERFALL')
        cr.move_to(right - 160, 20)
        cr.show_text('SPECTRUM  −90 → 0 dBFS')
        return False

    def _stop_capture(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            self.proc.stdout.close()
            self.proc = None
        self.pending = b''

    def _destroy(self, *_):
        self.alive = False
        GLib.source_remove(self.timer)
        self._stop_capture()
