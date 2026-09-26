#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""剥离内核源码里指向不存在文件/目录的引用（OPPO 开源树常见问题）。

要点：Kconfig 里的 source 路径是相对【内核源码根目录】的，不是相对当前文件。
用法: python3 fix_dangling.py <kernel根目录>
"""
import os, re, sys

root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '.')
kc = mk = mo = 0
missing_dirs = set()

def rel_ok(ref, base):
    p = os.path.normpath(os.path.join(base, ref))
    return os.path.exists(p), p

# ---- 1) Kconfig: source 相对根目录 ----
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
                if '$' not in ref:
                    ok, tgt = rel_ok(ref, root)          # ★ 相对根目录
                    if not ok:
                        missing_dirs.add(ref.split('/')[0])
                        print('[Kconfig] 删失效 source : %s -> %s' % (os.path.relpath(p, root), ref))
                        changed = True; kc += 1
                        continue
            out.append(ln)
        if changed:
            open(p, 'w', encoding='utf-8').write(''.join(out))

# ---- 2) Makefile: obj-* += 目录/ 和 目标.o（这两个相对当前文件目录） ----
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
            m = re.match(r'[ \t]*obj-[ym]?\s*\+=\s*([A-Za-z0-9_./+-]+)/[ \t]*$', ln)
            if m:
                ref = m.group(1)
                if '$' not in ref and not os.path.exists(os.path.normpath(os.path.join(dp, ref))):
                    missing_dirs.add(ref.split('/')[0])
                    print('[Makefile] 删失效目录 : %s -> %s/' % (os.path.relpath(p, root), ref))
                    changed = True; mk += 1
                    continue
                out.append(ln); continue
            m2 = re.match(r'[ \t]*obj-[ym]?\s*\+=\s*([A-Za-z0-9_./+-]+)\.o[ \t]*$', ln)
            if m2:
                ref = m2.group(1)
                if '$' not in ref:
                    b = os.path.normpath(os.path.join(dp, ref))
                    if not (os.path.exists(b+'.c') or os.path.exists(b+'.S') or os.path.exists(b+'.s')):
                        print('[Makefile] 删失效目标 : %s -> %s.o' % (os.path.relpath(p, root), ref))
                        changed = True; mo += 1
                        continue
            out.append(ln)
        if changed:
            open(p, 'w', encoding='utf-8').write(''.join(out))

print('')
print('=' * 62)
print('修复完成：Kconfig %d 条，Makefile 目录 %d 条，Makefile 目标 %d 条' % (kc, mk, mo))
if missing_dirs:
    print('涉及的缺失私有目录（顶层）: %s' % ', '.join(sorted(missing_dirs)[:20]))
print('=' * 62)
