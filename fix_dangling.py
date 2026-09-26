#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""删除内核源码里指向"不存在文件/目录"的引用（OPPO 开源树常见问题）。

用法:  python3 fix_dangling.py <kernel源码根目录>
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
kc = mk = mo = 0
skipped = []


def walk_files(exts=None, names=None):
    for dp, dn, fn in os.walk(root):
        if '.git' in dp.split(os.sep):
            continue
        for f in fn:
            if names and f in names:
                yield os.path.join(dp, f)
            elif exts and f.endswith(exts):
                yield os.path.join(dp, f)


# ---------- 1) Kconfig 里的 source 引用 ----------
for p in list(walk_files(exts='', names=None)) or []:
    pass

for dp, dn, fn in os.walk(root):
    if '.git' in dp.split(os.sep):
        continue
    for f in fn:
        if not f.startswith('Kconfig'):
            continue
        p = os.path.join(dp, f)
        try:
            txt = open(p, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        out, changed = [], False
        for ln in txt.splitlines(True):
            m = re.match(r'[ \t]*source\s+"([^"]+)"', ln)
            if m:
                ref = m.group(1)
                if '$' in ref:
                    skipped.append('%s -> %s' % (p, ref))
                    out.append(ln)
                    continue
                if not os.path.exists(os.path.normpath(os.path.join(dp, ref))):
                    print('[Kconfig] 删失效 source : %s -> %s' % (p, ref))
                    changed = True
                    kc += 1
                    continue
            out.append(ln)
        if changed:
            open(p, 'w', encoding='utf-8').write(''.join(out))

# ---------- 2) Makefile: obj-* += 目录/ 和 obj-* += 文件.o ----------
for dp, dn, fn in os.walk(root):
    if '.git' in dp.split(os.sep):
        continue
    for f in fn:
        if f not in ('Makefile', 'Kbuild'):
            continue
        p = os.path.join(dp, f)
        try:
            txt = open(p, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        out, changed = [], False
        for ln in txt.splitlines(True):
            # 目录形式
            m = re.match(r'[ \t]*obj-[ym]?\s*\+=\s*([A-Za-z0-9_./+-]+)/[ \t]*$', ln)
            if m:
                ref = m.group(1)
                if '$' not in ref and not os.path.exists(os.path.normpath(os.path.join(dp, ref))):
                    print('[Makefile] 删失效目录 : %s -> %s/' % (p, ref))
                    changed = True
                    mk += 1
                    continue
                out.append(ln)
                continue
            # 文件 .o 形式（同名 .c/.S 都不存在才删）
            m2 = re.match(r'[ \t]*obj-[ym]?\s*\+=\s*([A-Za-z0-9_./+-]+)\.o[ \t]*$', ln)
            if m2:
                ref = m2.group(1)
                if '$' not in ref:
                    base = os.path.normpath(os.path.join(dp, ref))
                    if not (os.path.exists(base + '.c') or os.path.exists(base + '.S')
                            or os.path.exists(base + '.s')):
                        print('[Makefile] 删失效目标 : %s -> %s.o' % (p, ref))
                        changed = True
                        mo += 1
                        continue
            out.append(ln)
        if changed:
            open(p, 'w', encoding='utf-8').write(''.join(out))

print('')
print('=' * 62)
print('修复完成：Kconfig %d 条，Makefile 目录 %d 条，Makefile 目标 %d 条' % (kc, mk, mo))
if skipped:
    print('跳过含变量的引用 %d 条（前 3）：' % len(skipped))
    for s in skipped[:3]:
        print('   ' + s)
print('=' * 62)
