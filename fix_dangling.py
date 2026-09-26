#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""剥离内核源码里指向不存在目标的引用（OPPO 开源树不完整）。

要点：
  1) Kconfig 的 source 路径有两种写法：相对【源码根目录】或相对【当前文件所在目录】
     -> 两种都试，都不存在才删
  2) Makefile 里的 obj-* += dir/ 相对当前文件目录
  3) 不碰 obj-* += xxx.o（那是合法写法，删了会坏驱动）
  4) 反复迭代直到没有新变化
用法: python3 fix_dangling.py <kernel根目录>
"""
import os, re, sys

root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '.')
missing_top = set()


def exists_any(ref, base):
    """ref 相对 base 或相对 root 存不存在"""
    for b in (base, root):
        if os.path.exists(os.path.normpath(os.path.join(b, ref))):
            return True
    return False


def one_pass():
    kc = mk = 0
    # --- Kconfig ---
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
                    if '$' not in ref and not exists_any(ref, dp):
                        missing_top.add(ref.rsplit('/', 1)[0] if '/' in ref else ref)
                        print('[Kconfig] 删  %s -> %s' % (os.path.relpath(p, root), ref))
                        changed = True
                        kc += 1
                        continue
                out.append(ln)
            if changed:
                open(p, 'w', encoding='utf-8').write(''.join(out))

    # --- Makefile 目录引用 ---
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
                    if '$' not in ref and not exists_any(ref, dp):
                        missing_top.add(ref.rsplit('/', 1)[0] if '/' in ref else ref)
                        print('[Makefile] 删  %s -> %s/' % (os.path.relpath(p, root), ref))
                        changed = True
                        mk += 1
                        continue
                out.append(ln)
            if changed:
                open(p, 'w', encoding='utf-8').write(''.join(out))
    return kc, mk


print('=== 开始迭代剥离失效引用 ===')
total_k = total_m = 0
for i in range(1, 11):
    kc, mk = one_pass()
    print('--- 第 %d 轮：Kconfig %d 条，Makefile %d 条 ---' % (i, kc, mk))
    total_k += kc
    total_m += mk
    if kc == 0 and mk == 0:
        print('=== 已收敛（第 %d 轮无变化）===' % i)
        break

print('')
print('=' * 62)
print('累计：Kconfig %d 条，Makefile 目录 %d 条' % (total_k, total_m))
if missing_top:
    print('涉及的缺失路径（前 25 个）:')
    for x in sorted(missing_top)[:25]:
        print('   ' + x)
print('=' * 62)
