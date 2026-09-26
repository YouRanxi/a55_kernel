#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动愈合不完整的内核源码树（OPPO 开源包经典问题）。

A. 反复跑 make <defconfig>；报 can't open file "X" 就创建空占位 X，重试
B. 反复跑 make；报 No rule to make target 'X' 就注释掉引用它的那行，重试
用法: python3 autoheal.py <kernel根目录> <defconfig名>
"""
import os, re, subprocess, sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '.')
DEF  = sys.argv[2] if len(sys.argv) > 2 else 'k6833v1_64_k419_defconfig'
MAKE = ['make','ARCH=arm64','O=out','CC=clang','CLANG_TRIPLE=aarch64-linux-gnu-',
        'CROSS_COMPILE=aarch64-linux-gnu-','CROSS_COMPILE_ARM32=arm-linux-gnueabi-']

def run(args, timeout=7200):
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, errors='replace', timeout=timeout)
    return p.returncode, (p.stdout or '') + (p.stderr or '')

def stub(rel):
    tgt = os.path.join(ROOT, rel)
    if os.path.exists(tgt):
        return False
    d = os.path.dirname(tgt)
    if d:
        os.makedirs(d, exist_ok=True)
    open(tgt, 'w').write('# auto-stub: 原厂开源包中缺失，用空配置占位\n')
    print('[stub] 创建空占位: %s' % rel)
    return True

def comment_out(leaf):
    done = 0
    for dp, dn, fn in os.walk(ROOT):
        if '.git' in dp.split(os.sep):
            continue
        for f in fn:
            if f not in ('Makefile','Kbuild') and not f.startswith('Kconfig'):
                continue
            p = os.path.join(dp, f)
            try:
                lines = open(p, encoding='utf-8', errors='replace').read().splitlines(True)
            except Exception:
                continue
            out, ch = [], False
            for ln in lines:
                s = ln.strip()
                if not s.startswith('#') and (s.startswith('obj-') or s.startswith('source')) and leaf in ln:
                    out.append('# auto-disabled: ' + ln)
                    ch = True; done += 1
                    print('[disable] %s : %s' % (os.path.relpath(p, ROOT), s[:90]))
                    continue
                out.append(ln)
            if ch:
                open(p, 'w', encoding='utf-8').write(''.join(out))
    return done

print('==== A: 生成 defconfig（自动补占位）====')
for i in range(1, 81):
    rc, out = run(MAKE + [DEF])
    if rc == 0:
        print('  OK（第 %d 次）' % i); break
    m = re.search(r"can't open file \"([^\"]+)\"", out)
    if not m:
        print('  无法自动修复，末尾 25 行:'); [print('   ', l[:150]) for l in out.splitlines()[-25:]]
        sys.exit(1)
    if not stub(m.group(1)):
        print('  !! 已存在却仍缺失: %s' % m.group(1)); sys.exit(1)
else:
    print('  !! 超限'); sys.exit(1)

print('')
print('==== B: 完整编译（自动禁用缺失目标）====')
for i in range(1, 121):
    rc, out = run(MAKE + ['-j%d' % (os.cpu_count() or 4)])
    if rc == 0:
        print('  编译 OK（第 %d 次）' % i); break
    m = re.search(r"No rule to make target ['\"]([^'\"]+)['\"]", out)
    if m:
        leaf = os.path.basename(m.group(1))
        print('  第 %d 次: 缺目标 %s' % (i, m.group(1)))
        if comment_out(leaf):
            continue
        print('  !! 找不到引用处')
    else:
        print('  编译失败且无法自动修复，末尾 30 行:')
        [print('   ', l[:150]) for l in out.splitlines()[-30:]]
        sys.exit(1)
else:
    print('  !! 超限'); sys.exit(1)

print('')
print('==== 产物 ====')
for p in ['out/arch/arm64/boot/Image.gz-dtb','out/arch/arm64/boot/Image.gz','out/arch/arm64/boot/Image']:
    fp = os.path.join(ROOT, p)
    if os.path.exists(fp):
        print('  %s (%d 字节)' % (p, os.path.getsize(fp)))
