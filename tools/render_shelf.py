#!/usr/bin/env python3
"""Render a synthetic GTK shelf specimen without mapping a foreground window.

Uses the actual source stylesheet and eight original hero SVGs. All workspace,
time and status values are fabricated; no compositor, device or application
inventory is queried. Existing DISPLAY is used only for Gtk.OffscreenWindow.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
HEROES = (('apps','library'),('files','folder'),('terminal','development'),('windows','window'),
          ('code','document-code'),('calc','calculator'),('audio','audio-console'),('home','home'))


def render(output):
    with tempfile.TemporaryDirectory(prefix='rgl-shelf-specimen-') as temporary:
        # Isolate before importing GTK or resolving the stylesheet palette. Never
        # read a user's GTK CSS, token override, icon preference or application set.
        for key, folder in (('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_STATE_HOME','state')):
            path=Path(temporary)/folder;path.mkdir();os.environ[key]=str(path)
        os.environ.update(GDK_BACKEND='x11',GTK_THEME='Adwaita:dark',GSETTINGS_BACKEND='memory',NO_AT_BRIDGE='1')
        os.environ.pop('GTK3_MODULES',None);os.environ.pop('GTK_MODULES',None)
        import gi,cairo
        gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0');gi.require_version('GdkPixbuf','2.0')
        gi.require_version('Pango','1.0');gi.require_version('PangoCairo','1.0')
        from gi.repository import Gtk,Gdk,GdkPixbuf,Pango,PangoCairo
        ready,_=Gtk.init_check([])
        if not ready:raise RuntimeError('GTK X11 offscreen display is unavailable; no foreground fallback is used')
        sys.path.insert(0,str(ROOT))
        from rglauncher_linux.shelf_design import stylesheet
        settings=Gtk.Settings.get_default();settings.set_property('gtk-enable-animations',False)
        provider=Gtk.CssProvider();errors=[]
        provider.connect('parsing-error',lambda _provider,_section,error:errors.append(str(error)))
        provider.load_from_data(stylesheet(root=ROOT).encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        if errors:raise RuntimeError('Source shelf CSS failed: '+'; '.join(errors))

        def box(css=None,spacing=0):
            result=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=spacing)
            if css:result.get_style_context().add_class(css)
            return result

        def image(module,identity,size,hero=False):
            container=box();container.set_name('image');container.get_style_context().add_class('rgl-'+module)
            if hero:file=ROOT/'assets/shelf-icons'/('aether-'+identity+'.svg')
            else:
                files=sorted((ROOT/'share/icons/aether-score/24x24').glob('*/aether-'+identity+'.svg'))
                if not files:raise RuntimeError('Missing original utility icon: '+identity)
                file=files[0]
            pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(file),size,size,True)
            widget=Gtk.Image.new_from_pixbuf(pixbuf);widget.set_valign(Gtk.Align.CENTER)
            container.pack_start(widget,False,False,0);container.set_valign(Gtk.Align.CENTER)
            return container

        def capture(size):
            window=Gtk.OffscreenWindow();window.set_name('waybar');window.set_default_size(1360,96)
            # This is always an offscreen native surface; no Gtk.Window fallback.
            root=box(spacing=4);window.add(root)
            left=box('modules-left',4);middle=box('modules-center',4);right=box('modules-right',4)
            root.pack_start(left,False,False,0);root.set_center_widget(middle);root.pack_end(right,False,False,0)
            workspaces=box();workspaces.set_name('workspaces')
            for number in ('1','2','3'):
                button=Gtk.Button(label=number);button.set_relief(Gtk.ReliefStyle.NONE)
                if number=='2':button.get_style_context().add_class('active')
                workspaces.pack_start(button,False,False,0)
            left.pack_start(workspaces,False,False,0)
            clock=Gtk.Label(label='10:24');clock.set_name('clock');left.pack_start(clock,False,False,0)
            for module,identity in HEROES:middle.pack_start(image(module,identity,size,True),False,False,0)
            for module,value in (('pulseaudio','62%'),('network','Wired')):
                label=Gtk.Label(label=value);label.set_name(module);label.set_valign(Gtk.Align.CENTER)
                right.pack_start(label,False,False,0)
            for module,identity in (('tools','utilities'),('background','more'),('settings','settings')):
                right.pack_start(image(module,identity,24),False,False,0)
            window.show_all()
            for _ in range(12):
                while Gtk.events_pending():Gtk.main_iteration_do(False)
                time.sleep(.01)
            pixbuf=window.get_pixbuf()
            if pixbuf is None:raise RuntimeError('Native GTK offscreen shelf produced no pixels')
            facts={'hero_size':size,'width':pixbuf.get_width(),'height':pixbuf.get_height()}
            if facts['width']>1360 or facts['height']>104:
                raise RuntimeError('Synthetic shelf exceeded its intended bounds: '+str(facts))
            # Copy pixels before destroying the native offscreen widget.
            copied=pixbuf.copy();window.destroy()
            while Gtk.events_pending():Gtk.main_iteration_do(False)
            return copied,facts

        rows=[capture(size) for size in (48,40)]
        width=1408;height=336
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,height);ctx=cairo.Context(surface)
        ctx.set_source_rgb(7/255,11/255,18/255);ctx.paint()
        def text(value,x,y,size,color):
            ctx.set_source_rgb(*(int(color[i:i+2],16)/255 for i in (1,3,5)));ctx.move_to(x,y)
            layout=PangoCairo.create_layout(ctx);font=Pango.FontDescription.from_string('Sans')
            font.set_absolute_size(size*Pango.SCALE);layout.set_font_description(font)
            layout.set_text(value,-1);PangoCairo.show_layout(ctx,layout)
        text('Instrument / Score Aether · Shelf',24,12,21,'#edf4ff')
        text('GTK OFFSCREEN VISUAL SPECIMEN · SAMPLE WORKSPACES, TIME AND STATUS · NO LIVE SESSION DATA',24,43,11,'#a3b3c9')
        for index,(pixbuf,facts) in enumerate(rows):
            y=76+index*128
            text(str(facts['hero_size'])+'px original object illustrations',28,y,11,'#a3b3c9')
            Gdk.cairo_set_source_pixbuf(ctx,pixbuf,(width-pixbuf.get_width())/2,y+19);ctx.paint()
        output.parent.mkdir(parents=True,exist_ok=True);surface.write_to_png(str(output))
        return {'renderer':'GTK3 OffscreenWindow, source shelf stylesheet and original SVGs',
                'sample_values_only':True,'no_foreground_window':True,'css_errors':errors,'rows':[facts for _,facts in rows],
                'image':{'width':width,'height':height}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/images/shelf.png')
    args=parser.parse_args()
    print(json.dumps(render(args.output),indent=2))


if __name__=='__main__':main()
