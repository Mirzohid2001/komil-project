#!/usr/bin/env python3
"""ui_strings.py dan uz/ru django.po va .mo yaratadi."""
from __future__ import annotations

import struct
import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# import sibling
import importlib.util

spec = importlib.util.spec_from_file_location('ui_strings', ROOT / 'ui_strings.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
UI = mod.UI


def write_po(lang: str) -> Path:
    lines = [
        'msgid ""',
        'msgstr ""',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        f'"Language: {lang}\\n"',
        '"Plural-Forms: nplurals=1; plural=0;\\n"',
        '',
    ]
    for msgid, trans in sorted(UI.items(), key=lambda x: x[0].lower()):
        msgstr = trans.get(lang, '')
        def esc(s: str) -> str:
            return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        lines.append(f'msgid "{esc(msgid)}"')
        lines.append(f'msgstr "{esc(msgstr)}"')
        lines.append('')
    out = ROOT / lang / 'LC_MESSAGES' / 'django.po'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return out


def write_mo(po_path: Path, mo_path: Path) -> None:
    """Minimal .mo writer (no plural support beyond single msgstr)."""
    entries = []
    msgid = msgstr = None
    reading = None  # 'id' | 'str'
    for raw in po_path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if line.startswith('msgid '):
            if msgid is not None and msgstr is not None:
                entries.append((msgid, msgstr))
            msgid = _unquote(line[6:])
            msgstr = None
            reading = 'id'
        elif line.startswith('msgstr '):
            msgstr = _unquote(line[7:])
            reading = 'str'
        elif line.startswith('"') and reading == 'id' and msgid is not None:
            msgid += _unquote(line)
        elif line.startswith('"') and reading == 'str' and msgstr is not None:
            msgstr += _unquote(line)
    if msgid is not None and msgstr is not None:
        entries.append((msgid, msgstr))

    # Deduplicate by msgid (last wins); empty msgid (header) must stay first
    mapping = {k: v for k, v in entries}
    keys = sorted(mapping.keys(), key=lambda k: (k != '', k.lower()))
    offsets = []
    ids = b''
    strs = b''
    for k in keys:
        v = mapping[k]
        kb = k.encode('utf-8') + b'\0'
        vb = v.encode('utf-8') + b'\0'
        offsets.append((len(kb), len(ids), len(vb), len(strs)))
        ids += kb
        strs += vb

    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + len(ids)
    output = array.array('I')
    output.append(0x950412DE)  # magic
    output.append(0)  # revision
    output.append(len(keys))
    output.append(7 * 4)  # key table offset
    output.append(7 * 4 + 8 * len(keys))  # value table offset
    output.append(0)
    output.append(0)
    k_off = keystart
    v_off = valuestart
    for i, k in enumerate(keys):
        klen, kpos, vlen, vpos = offsets[i]
        output.append(klen - 1)
        output.append(k_off + kpos)
    for i, k in enumerate(keys):
        klen, kpos, vlen, vpos = offsets[i]
        output.append(vlen - 1)
        output.append(v_off + vpos)
    mo_path.write_bytes(output.tobytes() + ids + strs)


def _unquote(s: str) -> str:
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return (
        s.replace('\\n', '\n')
        .replace('\\"', '"')
        .replace('\\\\', '\\')
    )


def main():
    for lang in ('uz', 'ru'):
        po = write_po(lang)
        mo = po.with_suffix('.mo')
        write_mo(po, mo)
        print(f'OK {lang}: {po} + {mo.name} ({len(UI)} strings)')


if __name__ == '__main__':
    main()
