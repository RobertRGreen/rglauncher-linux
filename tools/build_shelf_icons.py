#!/usr/bin/env python3
"""Original MIT shelf-object SVGs; optional native offscreen render/contact sheets.

No third-party paths, fonts, bitmap assets, SVG filters or application logos.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('library', 'folder', 'development', 'window', 'document-code', 'calculator', 'audio-console', 'home')
LABELS = ('Application library', 'Files', 'Terminal', 'Windows', 'Code document', 'Calculator', 'Audio Console', 'Home')


def path(d, fill='none', stroke=None, width=1.4, **extra):
    attrs = {'d':d, 'fill':fill}
    if stroke: attrs.update(stroke=stroke, **{'stroke-width':str(width), 'stroke-linecap':'round', 'stroke-linejoin':'round'})
    attrs.update({k.replace('_','-'):str(v) for k,v in extra.items()})
    return ET.Element('path',attrs)


def rect(x,y,w,h,r=0,fill='none',stroke=None,width=1.4,**extra):
    attrs = {'x':str(x),'y':str(y),'width':str(w),'height':str(h),'rx':str(r),'fill':fill}
    if stroke:attrs.update(stroke=stroke,**{'stroke-width':str(width)})
    attrs.update({k.replace('_','-'):str(v) for k,v in extra.items()})
    return ET.Element('rect',attrs)


def shapes(name,p):
    body='url(#body)';rim='url(#rim)';glass='url(#glass)';edge='url(#edge)'
    c,v,ink,shadow=p['cyan'],p['violet'],p['ink'],p['shadow']
    result=[]
    add=lambda *elements:result.extend(elements)
    if name=='library':
        # Four actual library objects, not a tile placed behind the whole icon.
        for x,y in ((9,10),(36,10),(9,36),(36,36)):
            add(rect(x+2,y+3,19,18,4,shadow),rect(x,y,19,18,4,body,rim,1.5),
                path(f'M{x+4} {y+2.6}H{x+13}',stroke=ink,width=1.1,opacity='.65'),
                path(f'M{x+17} {y+5}V{y+13}',stroke=c,width=.8,opacity='.45'),
                path(f'M{x+4} {y+15.5}H{x+14}',stroke=v,width=1,opacity='.65'))
    elif name=='folder':
        add(path('M8 22V14Q8 11 11 11H23L28 16H51Q54 16 54 19V46H8Z',body,rim,1.6),
            path('M12 22L16 16H43L48 22V44H12Z',glass,c,1),
            path('M17 23L21 18H48L52 24V46H17Z',p['paper'],ink,.8,opacity='.85'),
            path('M7 25H55Q58 25 57 29L53 51Q52.5 54 49 54H14Q10.5 54 10 51L6 29Q5.3 25 7 25Z',body,rim,1.8),
            path('M10 51Q11 55 14 55H49Q53 55 54 51L53 55Q52 58 48 58H15Q11 58 10 55Z',edge),
            path('M11 29H49',stroke=ink,width=1.2,opacity='.6'),
            path('M14 34H46',stroke=c,width=.85,opacity='.24'),
            path('M16 51H45',stroke=v,width=1.1,opacity='.72'))
    elif name=='development':
        add(rect(7,13,50,41,6,shadow),rect(6,10,50,41,6,body,rim,1.7),
            rect(10,16,42,29,3,p['recess'],p['boundary'],.8),
            path('M14 14H46',stroke=ink,width=1,opacity='.6'),
            path('M17 25L25 31L17 37',stroke=c,width=2.7),
            path('M31 38H41',stroke=ink,width=2.2),
            path('M14 49H46',stroke=v,width=1.2,opacity='.7'),
            path('M16 54H48L45 57H19Z',edge))
    elif name=='window':
        add(rect(19,7,39,34,5,body,v,1.4),path('M23 12H52',stroke=ink,width=.9,opacity='.65'),
            rect(7,21,43,34,5,shadow),rect(6,18,43,34,5,body,rim,1.7),
            path('M7 28H48',stroke=c,width=1.2,opacity='.7'),
            rect(11,33,12,13,2,glass,c,.7),rect(27,33,16,4,1,p['paper']),
            rect(27,41,12,3,1,p['paper'],opacity='.55'),
            path('M12 22H31',stroke=ink,width=1,opacity='.65'),
            path('M12 50H42',stroke=v,width=1.1,opacity='.7'))
    elif name=='document-code':
        add(path('M17 8H39L51 20V54Q51 58 47 58H17Q14 58 14 55V12Q14 8 17 8Z',shadow),
            path('M15 5H37L49 17V51Q49 55 45 55H15Q12 55 12 52V9Q12 5 15 5Z',body,rim,1.6),
            path('M37 5V14Q37 18 41 18H49Z',glass,v,1.2),
            path('M17 10H31',stroke=ink,width=1.1,opacity='.65'),
            path('M24 27L18 33L24 39M37 27L43 33L37 39',stroke=c,width=2.3),
            path('M33 26L28 40',stroke=ink,width=1.9),
            path('M20 47H39',stroke=v,width=1.2,opacity='.72'))
    elif name=='calculator':
        add(rect(14,7,37,52,7,shadow),rect(12,5,37,51,7,body,rim,1.7),
            rect(17,11,27,12,2.5,p['recess'],c,1),
            path('M21 15H39',stroke=ink,width=.9,opacity='.4'),
            path('M21 20H36',stroke=c,width=.9,opacity='.35'))
        for y in (29,39):
            for x in (18,28,38):
                add(rect(x,y+1.5,7,7,1.7,shadow),rect(x,y,7,6,1.7,glass,c if x==38 else p['boundary'],.8))
        add(path('M21 51H40',stroke=v,width=1.15,opacity='.7'))
    elif name=='audio-console':
        add(path('M12 14H51L58 53Q58.5 57 54 58H10Q6 57 6.5 53Z',shadow),
            path('M11 10H50L57 49Q57.5 53 53 54H9Q5 53 5.5 49Z',body,rim,1.7),
            path('M13 15H47',stroke=ink,width=1.1,opacity='.6'),
            path('M9 53H54L52 57H11Z',edge))
        for x,y in ((18,28),(31,33),(44,25)):
            add(rect(x-1.2,22,2.4,23,1.2,p['recess'],p['boundary'],.6),
                rect(x-5,y+1.5,10,6,2,shadow),rect(x-5,y,10,5,2,glass,c,1),
                path(f'M{x-2.5} {y+1.8}H{x+2.5}',stroke=ink,width=.9,opacity='.7'))
    elif name=='home':
        add(path('M12 28L32 11L53 28V54Q53 57 50 57H14Q11 57 11 54Z',shadow),
            path('M12 27L31 10L50 27V51Q50 54 47 54H15Q12 54 12 51Z',body,rim,1.6),
            path('M31 10L50 27V51Q50 54 47 54H43V26Z',edge,v,.9),
            path('M7 28L29 7Q31 5 34 7L56 27L51 31L32 14L12 32Z',glass,rim,1.7),
            path('M12 27L31 10',stroke=ink,width=1.1,opacity='.7'),
            path('M25 53V35Q25 33 27 33H35Q37 33 37 35V53Z',p['recess'],c,1.2),
            path('M16 51H22M40 51H46',stroke=v,width=1.1,opacity='.7'))
    return result


def svg(name,light,tokens):
    if light:
        p={'top':'#eff8ff','bottom':'#a3bdd7','glass_top':'#e2f7ff','glass_bottom':'#b8c9e9',
           'cyan':'#006b80','violet':'#6946a3','ink':'#ffffff','shadow':'#7e98b3',
           'paper':'#f5fbff','recess':'#e6f0f8','boundary':'#60829c','edge_violet':'#9d8ac0'}
    else:
        c=tokens['color']
        p={'top':'#3a6077','bottom':c['surface'],'glass_top':'#496780','glass_bottom':'#26334f',
           'cyan':c['selection'],'violet':c['focus'],'ink':c['text'],'shadow':'#060b14',
           'paper':'#7590ae','recess':'#0b1422','boundary':'#597d96','edge_violet':'#665d8c'}
    root=ET.Element('svg',{'xmlns':'http://www.w3.org/2000/svg','width':'64','height':'64','viewBox':'0 0 64 64','role':'img','aria-labelledby':'title desc'})
    ET.SubElement(root,'title',{'id':'title'}).text=LABELS[NAMES.index(name)]
    ET.SubElement(root,'desc',{'id':'desc'}).text='Original Instrument/Score Aether shelf object. Identity illustration, not live device state.'
    defs=ET.SubElement(root,'defs')
    for gid,a,b in [('body',p['top'],p['bottom']),('glass',p['glass_top'],p['glass_bottom']),('rim',p['cyan'],p['violet']),('edge',p['bottom'],p['edge_violet'])]:
        gradient=ET.SubElement(defs,'linearGradient',{'id':gid,'x1':'0','y1':'0','x2':'0.6','y2':'1'})
        ET.SubElement(gradient,'stop',{'offset':'0','stop-color':a})
        ET.SubElement(gradient,'stop',{'offset':'1','stop-color':b})
    root.extend(shapes(name,p))
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!-- Original geometry, MIT; Robert R Green and contributors. -->\n'+ET.tostring(root,encoding='unicode')+'\n'


def render(destination,output):
    import gi,cairo
    gi.require_version('Rsvg','2.0');gi.require_version('Pango','1.0');gi.require_version('PangoCairo','1.0')
    from gi.repository import Rsvg,Pango,PangoCairo
    output.mkdir(parents=True,exist_ok=True)
    cases=[]
    def color(ctx,h):ctx.set_source_rgb(*(int(h[i:i+2],16)/255 for i in (1,3,5)))
    def text(ctx,value,x,y,fg,size=12):
        color(ctx,fg);ctx.move_to(x,y)
        layout=PangoCairo.create_layout(ctx);font=Pango.FontDescription.from_string('Sans')
        font.set_absolute_size(size*Pango.SCALE);layout.set_font_description(font);layout.set_text(value,-1);PangoCairo.show_layout(ctx,layout)
    for light,bg,fg in [(False,'#090e18','#edf4ff'),(True,'#f2f5fa','#16344d')]:
        edition='bright' if light else 'dark'
        for size in (40,48,64):
            sheet=cairo.ImageSurface(cairo.FORMAT_ARGB32,8*144,132);ctx=cairo.Context(sheet)
            color(ctx,bg);ctx.paint();text(ctx,f'Instrument / Score Aether — shelf objects · {size}px · {edition}',18,12,fg,15)
            for i,name in enumerate(NAMES):
                file=destination/f'aether-{name}{"-light" if light else ""}.svg'
                handle=Rsvg.Handle.new_from_file(str(file));image=cairo.ImageSurface(cairo.FORMAT_ARGB32,size,size);cr=cairo.Context(image)
                bounds=Rsvg.Rectangle();bounds.x=bounds.y=0;bounds.width=bounds.height=size
                assert handle.render_document(cr,bounds)
                ctx.set_source_surface(image,i*144+(144-size)/2,40);ctx.paint()
                text(ctx,LABELS[i],i*144+10,109,fg,11)
                image.write_to_png(str(output/f'{name}-{edition}-{size}.png'))
                data=bytes(image.get_data());stride=image.get_stride()
                filled=sum(data[y*stride+x*4+3]>0 for y in range(size) for x in range(size))
                opaque=sum(data[y*stride+x*4+3]>=240 for y in range(size) for x in range(size))
                border=sum(data[y*stride+x*4+3]>0 for y in range(size) for x in range(size) if x in (0,size-1) or y in (0,size-1))
                assert filled>0 and border==0
                cases.append({'identity':name,'edition':edition,'size':size,'ink_pixels':filled,'opaque_pixels':opaque,'edge_pixels':border})
            sheet.write_to_png(str(output/f'contact-{edition}-{size}.png'))
    (output/'render-report.json').write_text(json.dumps({'renderer':'Native librsvg/Cairo','identities':8,'svg_count':16,
        'svg_sha256':{file.name:hashlib.sha256(file.read_bytes()).hexdigest() for file in sorted(destination.glob('*.svg'))},'cases':cases},indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'assets/shelf-icons')
    parser.add_argument('--tokens',type=Path,default=ROOT/'share/instrument-score-aether/tokens.json')
    parser.add_argument('--render',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    tokens=json.loads(args.tokens.read_text())
    for light in (False,True):
        for name in NAMES:(args.output/f'aether-{name}{"-light" if light else ""}.svg').write_text(svg(name,light,tokens))
    if args.render:render(args.output,args.render)
    print('Generated 8 original shelf identities, 16 SVGs; no installation performed.')


if __name__=='__main__':main()
