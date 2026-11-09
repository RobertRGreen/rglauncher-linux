"""A small, keyboard-accessible control room for the installed desktop shell."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from . import __version__
from .paths import config_dir, release_root


def main(*, window_class=None, run_loop=True):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib
    sys.path.insert(0, str(release_root()/'bin'))
    from _cyber_theme import BG, BG_CARD, FG, MUTED, LINE, CONTROL_LINE, PURPLE, ACCENT2, FONT_BODY, FONT_MONO
    from _aether_material import surface_declarations
    window = (window_class or Gtk.Window)(title='RGLauncher · Control Room')
    window.set_default_size(900, 660)
    window.set_position(Gtk.WindowPosition.CENTER)
    window.get_style_context().add_class('rgl-settings')
    provider = Gtk.CssProvider()
    provider.load_from_data(f'''
    window.rgl-settings {{background:{BG};color:{FG};font-family:"{FONT_BODY}";font-size:14px;}}
    .rgl-settings .shell {{{surface_declarations(22)} padding:28px;}}
    .rgl-settings .title {{font-size:30px;font-weight:600;}}
    .rgl-settings .subtitle {{color:{MUTED};}}
    .rgl-settings .mono {{font-family:"{FONT_MONO}";font-size:12px;color:{ACCENT2};}}
    .rgl-settings .plane {{background:{BG_CARD};border:1px solid {LINE};border-radius:16px;padding:20px;}}
    .rgl-settings .heading {{font-size:18px;font-weight:600;}}
    .rgl-settings button {{background:{BG_CARD};color:{FG};border:1px solid {CONTROL_LINE};border-radius:9px;padding:9px 13px;}}
    .rgl-settings button:hover {{border-color:{ACCENT2};}}
    .rgl-settings button:focus {{border-color:{PURPLE};outline:2px solid {PURPLE};outline-offset:2px;}}
    .rgl-settings button:disabled {{color:{MUTED};}}
    .rgl-settings switch:checked {{background:{PURPLE};}}
    '''.encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    scroller = Gtk.ScrolledWindow(); scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18); shell.get_style_context().add_class('shell')
    scroller.add(shell); window.add(scroller)

    def label(text, css=None):
        result = Gtk.Label(label=text, xalign=0); result.set_line_wrap(True)
        if css: result.get_style_context().add_class(css)
        return result

    shell.pack_start(label('RGLauncher', 'title'), False, False, 0)
    shell.pack_start(label('Linux Edition  /  Instrument · Score · Aether', 'subtitle'), False, False, 0)
    shell.pack_start(label('DESKTOP SHELL  ·  '+__version__, 'mono'), False, False, 0)
    content = Gtk.Box(spacing=16); content.set_homogeneous(True); shell.pack_start(content, True, True, 0)
    window.connect('size-allocate', lambda _w, allocation: content.set_orientation(
        Gtk.Orientation.VERTICAL if allocation.width < 760 else Gtk.Orientation.HORIZONTAL))
    work = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); work.get_style_context().add_class('plane')
    updates = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12); updates.get_style_context().add_class('plane')
    content.pack_start(work, True, True, 0); content.pack_start(updates, True, True, 0)
    work.pack_start(label('Your workbench', 'heading'), False, False, 0)
    work.pack_start(label('Applications, files, calculation and sound share one familiar instrument.', 'subtitle'), False, False, 0)

    def launch(command):
        subprocess.Popen([sys.executable, '-B', str(release_root()/'bin/rglauncher'), command], start_new_session=True)

    for title, command, icon in [('Applications', 'apps', 'aether-library'), ('Files', 'files', 'aether-folder'),
                                 ('Calculator', 'calc', 'aether-calculator'), ('Audio console', 'audio', 'aether-audio-console')]:
        button = Gtk.Button(label=title)
        button.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON)); button.set_always_show_image(True)
        button.connect('clicked', lambda _b, c=command: launch(c)); work.pack_start(button, False, False, 0)
    work.pack_start(label('Super + number  ·  Workspace\nSuper + arrows  ·  Tile\nShift + Super + arrows  ·  Thirds\nAlt + Tab  ·  Switch and release capture', 'subtitle'), False, False, 8)
    updates.pack_start(label('Release & updates', 'heading'), False, False, 0)
    status = label('Reading installed release…', 'mono'); updates.pack_start(status, False, False, 0)
    detail = label('', 'subtitle'); updates.pack_start(detail, False, False, 0)
    buttons = []

    def show_result(action, result, error=None):
        for button in buttons: button.set_sensitive(True)
        if error:
            detail.set_text(error); return False
        if action == 'status':
            status.set_text('INSTALLED  '+str(result.get('current_version') or __version__))
            detail.set_text('Channel: '+str(result.get('channel', 'unconfigured'))+'\n'+
                            ('Rollback available: '+str(result.get('previous_version')) if result.get('previous_version') else 'First managed release'))
        elif action == 'check':
            detail.set_text(('Available: '+str(result.get('available_version'))) if result.get('update_available') else 'You are up to date on this channel.')
        else:
            if result.get('changed'):
                detail.set_text('Release changed. New launches use the selected release. Refresh the desktop to reload its surfaces.')
                status.set_text('INSTALLED  '+str(result.get('version') or result.get('current_version') or __version__))
            else:
                detail.set_text('No release change. '+str(result.get('reason') or 'You already have the selected release.'))
        return False

    def run(action):
        for button in buttons: button.set_sensitive(False)
        if action != 'status': detail.set_text({'check':'Checking the signed release feed…', 'apply':'Verifying and installing…', 'rollback':'Verifying the previous release…'}[action])
        def worker():
            result = subprocess.run([sys.executable, '-B', str(release_root()/'bin/rglauncher'), 'update', action],
                                    capture_output=True, text=True)
            try:
                if result.returncode: raise RuntimeError((result.stderr or result.stdout).strip()[-600:])
                GLib.idle_add(show_result, action, json.loads(result.stdout))
            except (ValueError, RuntimeError) as error:
                GLib.idle_add(show_result, action, {}, str(error))
        threading.Thread(target=worker, daemon=True).start()

    for title, action in [('Check for updates', 'check'), ('Install verified update', 'apply'), ('Restore previous release', 'rollback')]:
        button = Gtk.Button(label=title); button.connect('clicked', lambda _b, a=action: run(a))
        buttons.append(button); updates.pack_start(button, False, False, 0)
    settings_path = config_dir()/'updates.json'
    try: settings = json.loads(settings_path.read_text())
    except (OSError, ValueError): settings = {}
    automatic = Gtk.CheckButton(label='Install signed updates automatically')
    automatic.set_active(bool(settings.get('automatic', False)))
    automatic.set_sensitive(bool(settings.get('feed_url')))
    def toggle(widget):
        # Timer remains available; its command also checks this explicit choice.
        try:
            desired = widget.get_active()
            if desired:
                result = subprocess.run(['systemctl', '--user', 'enable', '--now', 'rglauncher-update.timer'], capture_output=True, text=True, timeout=15)
                if result.returncode: raise RuntimeError('Update timer could not start: '+result.stderr.strip()[-250:])
            data = json.loads(settings_path.read_text()); data['automatic'] = desired
            temp = settings_path.with_suffix('.tmp'); temp.write_text(json.dumps(data, indent=2)+'\n'); temp.chmod(0o600); os.replace(temp, settings_path)
            detail.set_text('Automatic signed updates enabled.' if desired else 'Automatic installs disabled. Manual checks remain available.')
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            detail.set_text(str(error))
            widget.handler_block(toggle_handler); widget.set_active(not widget.get_active()); widget.handler_unblock(toggle_handler)
    toggle_handler = automatic.connect('toggled', toggle); updates.pack_start(automatic, False, False, 8)
    shell.pack_start(label('Reveal the shelf at the bottom edge. It floats above windows and gives the space back when you leave.', 'subtitle'), False, False, 0)
    window.connect('key-press-event', lambda _w, event: (window.close() or True) if event.keyval == Gdk.KEY_Escape else False)
    refresh = Gtk.Button(label='Refresh desktop surfaces')
    refresh.connect('clicked', lambda _b: subprocess.Popen([sys.executable, '-B', str(release_root()/'bin/rglauncher'), 'desktop', 'refresh']))
    shell.pack_start(refresh, False, False, 0)
    window.connect('destroy', lambda *_: Gtk.main_quit() if Gtk.main_level() else None); window.show_all()
    if not run_loop:
        status.set_text('INSTALLED  '+__version__)
        detail.set_text('Channel: prerelease\nSigned releases · rollback available')
        return window
    run('status'); Gtk.main()
    return 0
