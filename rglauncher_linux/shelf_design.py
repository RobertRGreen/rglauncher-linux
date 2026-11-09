"""Compose the icon shelf without rewriting the user's Waybar actions.

A continuous, bounded deck replaces edge-to-edge telemetry islands. Icons are
real project SVGs; names/shortcuts live in native tooltips, never font glyphs.
"""
from __future__ import annotations
import copy
import html
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def icon_path(name, root=ROOT, size=48):
    hero=Path(root)/'assets/shelf-icons'/('aether-'+name+'.svg')
    if size == 48 and hero.is_file():return hero
    candidates = sorted((Path(root)/'share/icons/aether-score'/f'{size}x{size}').glob('*/aether-'+name+'.svg'))
    if not candidates:
        raise ValueError('Missing shelf icon: '+name)
    return candidates[0]


def image(name, icon, title, action=None, *, root=ROOT, size=36):
    # Image's native API expects newline-delimited path and tooltip, not JSON.
    data = {'exec':shlex.join(['printf','%s\n%s\n',str(icon_path(icon,root)),html.escape(title)]),
            'interval':'once','size':size,'tooltip':True}
    if action: data['on-click'] = action
    return 'image#rgl-'+name, data


def compose(base, monitor, *, root=ROOT):
    config = copy.deepcopy(base)
    width = monitor['height' if monitor.get('transform',0)%2 else 'width']/(monitor.get('scale',1) or 1)
    compact = width < 1200
    tiny = width < 1100
    deck_width = min(1360 if width >= 1800 else 1200, int(width)-32)
    config.update({'output':monitor['name'],'position':'bottom','layer':'overlay','exclusive':False,
                   'width':deck_width,'height':96 if not tiny else 84,'spacing':4,'fixed-center':False,
                   'margin-left':0,'margin-right':0,'margin-top':0,'margin-bottom':12,
                   'start_hidden':True,'passthrough':False,'on-sigusr1':'toggle','on-sigusr2':'reload'})
    config.pop('mode',None)
    command = lambda name: shlex.join([sys.executable,'-B',str(Path(root)/'bin/rglauncher'),name])
    pins = [('apps','library','Applications · Super+Space',command('apps')),
            ('files','folder','Files · Super+D',command('files')),
            ('terminal','development','Terminal · Super+Q',command('terminal')),
            ('windows','window','Windows · Super+Tab / Alt+Tab',command('windows')),
            ('calc','calculator','Calculator',command('calc')),
            ('audio','audio-console','Audio Console · routing, buses & EQ',command('audio'))]
    editor = shutil.which('code-oss') or shutil.which('code')
    if editor: pins.insert(4,('code','document-code','Code editor',shlex.join([editor])))
    if 'custom/hcp' in base and base['custom/hcp'].get('on-click'):
        pins.append(('home','home','Home Control Protocol',base['custom/hcp']['on-click']))
    primary, overflow = [], []
    for name, icon, title, action in pins:
        key, data = image(name,icon,title,action,root=root,size=36 if compact else 48)
        config[key]=data
        (overflow if compact and name in ('terminal','code','calc','home') else primary).append(key)
    for name,icon,title in [('tools','utilities','More instruments · click to expand'),
                            ('background','more','Background applications · click to expand'),
                            ('context','workspace','Workspaces · click to expand'),
                            ('settings','settings','Control Room · appearance & updates')]:
        key,data=image(name,icon,title,command('settings') if name=='settings' else None,root=root,size=24)
        config[key]=data
    left=[]
    workspaces='hyprland/workspaces'
    if workspaces in base:
        config[workspaces].update({'format':'{name}','disable-scroll':True,'sort-by-number':True})
        # Keep established workspace actions (including Lua backend activation).
        if tiny:
            config['group/rgl-context']={'orientation':'inherit','drawer':{'click-to-reveal':True,'transition-duration':0},'modules':['image#rgl-context',workspaces]}
            left.append('group/rgl-context')
        else:left.append(workspaces)
    if 'hyprland/submap' in base:left.append('hyprland/submap')
    config['clock']={**base.get('clock',{}),'format':'{:%H:%M}','format-alt':'{:%a %d %b}',
                     'tooltip-format':'{:%A, %d %B %Y}','interval':60}
    if not tiny:left.append('clock')
    config['group/rgl-launch']={'orientation':'inherit','modules':primary}
    right=[]
    for key in ('pulseaudio','network','bluetooth'):
        if key in base:
            right.append(key)
    if 'pulseaudio' in base:
        config['pulseaudio'].update({'format':'{volume}%','format-bluetooth':'{volume}%',
                                     'format-muted':'Muted','tooltip-format':'{desc} · {volume}%\nClick: Audio Console'})
    if 'network' in base:
        config['network'].update({'format-wifi':'Wi-Fi','format-ethernet':'Wired','format-disconnected':'Offline'})
    if 'bluetooth' in base:
        config['bluetooth'].update({'format':'On','format-disabled':'Off','format-off':'Off',
            'format-connected':'{num_connections}','format-connected-battery':'{num_connections}'})
    for key in ('custom/server','custom/remote'):
        if key in base:
            config[key]['max-length']=12
            if config[key].get('return-type') == 'json' and config[key].get('exec'):
                formatter=shlex.join([sys.executable,'-B',str(Path(root)/'bin/rglauncher'),'shelf','format-status','--output',key])
                config[key]['exec']='( '+config[key]['exec']+' ) | '+formatter
            right.append(key)
    # All remaining private/custom capabilities remain reachable with their exact
    # commands. Health and remote-control evidence stay outside disclosure.
    used=set(left+right+['clock','hyprland/workspaces','hyprland/submap','hyprland/window','custom/calc','custom/hcp'])
    extras=[]
    for region in ('modules-left','modules-center','modules-right'):
        for key in base.get(region,[]):
            if key not in used and key not in ('tray','custom/apps','custom/files','custom/windows','custom/settings'):
                extras.append(key);used.add(key)
    extras=overflow+extras
    if extras:
        config['image#rgl-tools']['on-click']=shlex.join([sys.executable,'-B',str(Path(root)/'bin/rglauncher'),'shelf','tools'])
        # A searchable chooser preserves targets without widening the deck.
        config['rgl-tool-items']=extras
        right.append('image#rgl-tools')
    if 'tray' in base:
        config['tray']={**base['tray'],'icon-size':22,'spacing':10}
        config['group/rgl-background']={'orientation':'inherit','drawer':{'click-to-reveal':True,'transition-duration':0,'transition-left-to-right':False},'modules':['image#rgl-background','tray']}
        right.append('group/rgl-background')
    right.append('image#rgl-settings')
    config.update({'modules-left':left,'modules-center':['group/rgl-launch'],'modules-right':right})
    return config


def clean_status(data, module):
    """Keep observed state/tooltip; category images replace legacy font icons."""
    if not isinstance(data,dict):raise ValueError('Status must be a JSON object')
    result=copy.deepcopy(data)
    text=re.sub('[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]','',str(result.get('text',''))).strip()
    if module=='custom/remote':
        state=result.get('class')
        text={'idle':'Idle','controlling':'Live','controlled':'Hosted'}.get(state,text) if isinstance(state,str) else text
    result['text']=text
    return result


def palette(root=ROOT):
    bundled=Path(root)/'share/instrument-score-aether/tokens.json'
    override=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'instrument-score-aether/tokens.json'
    tokens=json.loads((override if override.is_file() else bundled).read_text())
    if any(not re.fullmatch('#[0-9a-fA-F]{6}',c) for c in tokens['color'].values()):
        raise ValueError('Shelf colors must be six-digit hex values')
    return tokens


def stylesheet(*, root=ROOT, relative=False):
    t=palette(root);c=t['color'];bg=c['canvas'];surface=c['surface'];raised=c['raised'];fg=c['text'];muted=c['secondary'];line=c['boundary'];cyan=c['selection'];violet=c['focus']
    rgba=lambda h,a:'rgba('+','.join(str(int(h[i:i+2],16)) for i in (1,3,5))+','+str(a)+')'
    rules=f'''/* RGLauncher suspended instrument shelf. One deck, readable instruments. */
window#waybar {{
 background-color:{bg};
 background-image:linear-gradient(180deg,{rgba(fg,.065)},transparent 28%,{rgba(bg,.1)} 84%,{rgba(cyan,.07)}),
 radial-gradient(ellipse at 25% 0%,{rgba(cyan,.065)},transparent 60%),
 radial-gradient(ellipse at 80% 100%,{rgba(violet,.09)},transparent 60%);
 color:{fg}; border:1px solid {rgba(c['control_boundary'],.65)};
 border-top-color:{rgba(cyan,.58)};border-bottom:4px solid {rgba(line,.95)};
 border-radius:24px;
 box-shadow:inset 0 1px {rgba(fg,.12)},inset 0 -1px {rgba(violet,.3)},0 4px 12px {rgba(bg,.5)};
}}
window#waybar.hidden {{opacity:0;}}
window#waybar * {{font-family:{json.dumps(t['font']['reading'])};font-size:13px;text-shadow:none;min-height:0;}}
window#waybar .modules-left, window#waybar .modules-center, window#waybar .modules-right {{
 background:transparent;border:none;border-radius:0;box-shadow:none;padding:6px 10px;
}}
window#waybar .modules-center {{padding:3px 14px;border-left:1px solid {rgba(line,.7)};border-right:1px solid {rgba(line,.7)};margin:9px 0;}}
window#waybar #image {{background:transparent;border:none;box-shadow:none;border-radius:13px;padding:9px 10px;margin:2px 1px;min-width:24px;}}
window#waybar #image:hover {{background-color:{rgba(raised,.95)};box-shadow:inset 0 1px {rgba(cyan,.4)},inset 0 -2px {rgba(violet,.55)};}}
window#waybar #image.rgl-apps, window#waybar #image.rgl-files,window#waybar #image.rgl-terminal,
window#waybar #image.rgl-windows,window#waybar #image.rgl-code,window#waybar #image.rgl-calc,
window#waybar #image.rgl-audio,window#waybar #image.rgl-home {{
 background-image:linear-gradient(155deg,{rgba(raised,.55)},transparent 75%);
 border-top:1px solid {rgba(fg,.065)};border-bottom:2px solid {rgba(bg,.6)};
 margin:0 2px;min-width:40px;padding:8px 6px;
}}
window#waybar #image.rgl-apps {{background-color:{rgba(violet,.08)};}}
window#waybar #workspaces {{background:transparent;padding:0;margin:0 4px;border:none;}}
window#waybar #workspaces button {{min-width:32px;padding:8px 5px;margin:17px 1px;color:{muted};border:0;border-radius:9px;background:transparent;box-shadow:none;font-family:{json.dumps(t['font']['value'])};font-size:13px;}}
window#waybar #workspaces button.active {{color:{cyan};background:{raised};box-shadow:inset 0 -2px {cyan},inset 0 1px {rgba(cyan,.2)};}}
window#waybar #workspaces button.urgent {{color:{c['warning']};box-shadow:inset 0 -2px {c['warning']};}}
window#waybar #workspaces button:hover {{background:{raised};color:{fg};}}
window#waybar #clock {{background:transparent;border:0;margin:0 10px;padding:0 2px;min-width:54px;font-family:{json.dumps(t['font']['value'])};font-size:15px;color:{fg};}}
window#waybar #pulseaudio,window#waybar #network,window#waybar #bluetooth,
window#waybar #custom-server,window#waybar #custom-remote {{
 background-color:transparent;background-repeat:no-repeat;background-position:9px center;background-size:24px;
 border:0;border-radius:12px;margin:6px 1px;padding:9px 8px 9px 39px;min-width:16px;
 font-size:12px;color:{muted};
}}
window#waybar #pulseaudio:hover,window#waybar #network:hover,window#waybar #bluetooth:hover,
window#waybar #custom-server:hover,window#waybar #custom-remote:hover {{background-color:{raised};color:{fg};}}
window#waybar #network.disconnected,window#waybar #custom-server.down,window#waybar #custom-server.crit {{color:{c['danger']};box-shadow:inset 0 -2px {c['danger']};}}
window#waybar #custom-server.warn,window#waybar #custom-server.unlock,window#waybar #custom-server.boot,
window#waybar #custom-remote.controlling,window#waybar #custom-remote.controlled {{color:{c['warning']};box-shadow:inset 0 -2px {c['warning']};}}
window#waybar #cpu,window#waybar #memory,window#waybar #custom-gpu,window#waybar #battery,
window#waybar #custom-opencam,window#waybar #custom-vrdesk {{background:{surface};border:0;border-radius:10px;padding:6px 10px;margin:6px 2px;font-size:12px;min-width:0;}}
window#waybar #tray {{background:transparent;border:0;padding:0 6px;margin:0;}}
window#waybar #submap {{color:{c['warning']};border:1px solid {c['warning']};border-radius:8px;padding:6px;}}
tooltip {{background:{surface};border:1px solid {c['control_boundary']};border-radius:12px;box-shadow:0 8px 24px {rgba(bg,.8)};}}
tooltip label {{color:{fg};font-family:{json.dumps(t['font']['reading'])};font-size:13px;padding:9px 13px;}}
'''
    for module,icon in [('pulseaudio','speaker'),('network','network'),('bluetooth','bluetooth'),('custom-server','computer'),('custom-remote','remote')]:
        path=icon_path(icon,root,32)
        url=os.path.relpath(path,Path(root)/'share/waybar') if relative else path.as_uri()
        rules+='window#waybar #'+module+' {background-image:url("'+url+'");}\n'
    return rules
