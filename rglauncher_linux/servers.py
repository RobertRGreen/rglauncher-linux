"""Server-button integration. Status reads a cache; only the window starts SSH."""
from __future__ import annotations
import fcntl
import html
import json
import os
from pathlib import Path
import re
import subprocess
import time


def summary(hosts, snapshots):
    by_id={item.get('id'):item for item in snapshots}
    counts={};lines=[]
    for host in hosts:
        ident=host.id if hasattr(host,'id') else host['id']
        name=host.label if hasattr(host,'label') else host['label']
        item=by_id.get(ident,{})
        target=host.target if hasattr(host,'target') else host.get('target')
        port=host.port if hasattr(host,'port') else host.get('port')
        if ((target is not None and item.get('target') != target) or
                (port is not None and item.get('port') != port)):
            item={}
        if item.get('cache_active') is False and item.get('state') in ('online','live','connecting'):
            item={**item,'state':'stopped'}
        state=item.get('state','not_sampled');counts[state]=counts.get(state,0)+1
        title={'online':'Live','live':'Live','connecting':'Connecting','auth_required':'SSH authentication required',
               'host_key_error':'SSH host key requires review','unreachable':'Connection unavailable',
               'unsupported':'Shell / sampler unavailable','stale':'Stale reading','stopped':'Monitor closed',
               'error':'Diagnostics unavailable','not_sampled':'Not sampled yet'}.get(state,state.replace('_',' ').title())
        age=item.get('age')
        suffix=f' · last sample {max(0,int(age))}s ago' if isinstance(age,(int,float)) else ''
        if item.get('cache_active') is False and state not in ('stopped','stale','not_sampled'):
            title='Last attempt: '+title
        lines.append(html.escape(name+' — '+title+suffix))
    live=counts.get('online',0)+counts.get('live',0);total=len(hosts)
    cls='ok' if total and live==total else 'warn' if live else 'unknown'
    text=f'{live}/{total}' if live else 'Servers'
    caption='Live diagnostics while the Servers window is open. Closing it stops SSH sampling.'
    if not total:caption='No SSH targets configured. Open Servers to view setup instructions.'
    return {'text':text,'class':cls,'tooltip':'\n'.join([caption,*lines]),'alt':'servers'}


def status(waybar=False):
    from .fleet import load_hosts,load_cache,host_transport_id
    hosts=load_hosts();snapshots=load_cache()
    expected={host.id:host_transport_id(host) for host in hosts}
    snapshots=[row for row in snapshots if row.get('transport_id')==expected.get(row.get('id')) and row.get('id') in expected]
    result=summary(hosts,snapshots) if waybar else {'hosts':len(hosts),'snapshots':snapshots,'sampling':'on demand while window is open'}
    print(json.dumps(result));return 0


def focus_existing():
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):return
    try:
        rows=json.loads(subprocess.check_output(['hyprctl','clients','-j'],text=True,timeout=2))
        address=next((c.get('address','') for c in rows if c.get('title')=='Servers · RGLauncher'),'')
        if re.fullmatch(r'0x[0-9a-fA-F]+',address):
            subprocess.run(['hyprctl','eval','hl.dispatch(hl.dsp.focus({window="address:'+address+'"}))'],capture_output=True,timeout=2)
    except (OSError,ValueError,subprocess.SubprocessError):pass


def open_window():
    from .paths import state_dir
    directory=state_dir()/'fleet';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (directory/'window.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            focus_existing();return 0
        from .fleet_ui import main
        return main()
