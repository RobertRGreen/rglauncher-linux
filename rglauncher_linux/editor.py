"""Install the original VS Code extension and merge just its two preferences."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from .paths import release_root, state_dir


def jsonc_tokens(text):
    pattern = re.compile(r'\s+|//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|[{}\[\]:,]|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|.', re.S)
    for match in pattern.finditer(text):
        token = match.group()
        if not token.isspace() and not token.startswith(('//', '/*')):
            yield token, match.start(), match.end()


def load_jsonc(text):
    tokens = list(jsonc_tokens(text))
    return json.loads(''.join(token for i,(token,_,_) in enumerate(tokens)
                      if not (token == ',' and i+1 < len(tokens) and tokens[i+1][0] in ('}',']'))))


def merge_preferences(text, changes):
    """Preserve comments and unrelated JSONC formatting, including trailing commas."""
    tokens = list(jsonc_tokens(text))
    if not tokens or tokens[0][0] != '{' or tokens[-1][0] != '}':
        raise ValueError('Expected a VS Code JSONC settings object')
    # Validate syntax before editing. Comments/trailing commas are legal JSONC.
    load_jsonc(text)
    replacements, found, depth = [], set(), 0
    for index, (token, start, end) in enumerate(tokens):
        if token in ('{','['): depth += 1
        elif token in ('}',']'): depth -= 1
        elif depth == 1 and token.startswith('"') and index+1 < len(tokens) and tokens[index+1][0] == ':':
            key = json.loads(token)
            if key not in changes: continue
            if key in found: raise ValueError('Duplicate theme preference: '+key)
            found.add(key)
            first = index+2; last = first; nested = 0
            for last in range(first, len(tokens)):
                value = tokens[last][0]
                if nested == 0 and value in (',','}'): break
                if value in ('{','['): nested += 1
                elif value in ('}',']'): nested -= 1
            replacements.append((tokens[first][1], tokens[last-1][2], json.dumps(changes[key])))
    missing = {key: value for key, value in changes.items() if key not in found}
    if missing:
        end = tokens[-1][1]
        has_values = len(tokens) > 2
        prefix = ',' if has_values and tokens[-2][0] != ',' else ''
        insertion = prefix+'\n'+',\n'.join('    '+json.dumps(k)+': '+json.dumps(v) for k,v in missing.items())+'\n'
        replacements.append((end, end, insertion))
    for start,end,value in sorted(replacements, reverse=True): text = text[:start]+value+text[end:]
    return text


def install_editor(variant='night', executable=None):
    executable = executable or shutil.which('code-oss') or shutil.which('code')
    if not executable: return {'status':'editor_not_installed'}
    names = {'night':'RGLauncher Aether Night', 'opaque':'RGLauncher Aether Opaque', 'day':'RGLauncher Aether Day'}
    if variant not in names: raise ValueError('Unknown editor variant')
    archive = release_root()/'share/vscode/rglauncher-aether.vsix'
    if not archive.is_file(): raise RuntimeError('The release is missing its VS Code extension')
    result = subprocess.run([executable, '--install-extension', str(archive), '--force'], capture_output=True, text=True, timeout=120)
    if result.returncode: raise RuntimeError('Editor extension installation failed: '+result.stderr[-500:])
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')))
    # The installed executable's product metadata owns its application folder.
    product = Path('/usr/lib/code/product.json')
    application = 'Code - OSS' if 'oss' in Path(executable).name else 'Code'
    if product.is_file():
        metadata = json.loads(product.read_text())
        application = metadata.get('nameShort', application)
    path = config_home/application/'User/settings.json'
    original = path.read_text() if path.exists() else '{}\n'
    updated = merge_preferences(original, {'workbench.colorTheme':names[variant], 'workbench.iconTheme':'rglauncher-aether-files'})
    backups = state_dir()/'editor'/time.strftime('%Y%m%d-%H%M%S'); backups.mkdir(parents=True,exist_ok=True)
    if path.exists(): shutil.copy2(path, backups/'settings.json')
    else: (backups/'settings.absent').touch()
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_suffix('.rgl-tmp');temp.write_text(updated)
    temp.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600);os.replace(temp,path)
    receipt = {'status':'installed','theme':names[variant],'settings':str(path),'backup':str(backups),'extension':'rglauncher.rglauncher-aether'}
    (backups/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
