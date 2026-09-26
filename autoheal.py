#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动愈合不完整的内核源码树（OPPO 开源包经典问题）。

注意：GitHub 的 ZIP 会把符号链接变成普通文件，所以"路径存在但不是目录"要单独处理。
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

def key_from_target(t):
    """从 'No rule to make target X' 里提取最有辨识度的关键词"""
    t = t.replace('\\', '/')
    parts = [p for p in t.split('/') if p and p != '..' and p != '.']
    if parts and parts[-1] in ('Makefile', 'Kbuild', 'Kconfig'):
        parts = parts[:-1]
    return parts[-1] if parts else t


def stub(rel):
    """创建空占位文件。返回 True=成功；False=搞不定（调用方改走禁用引用）"""
    tgt = os.path.join(ROOT, rel)
    if os.path.exists(tgt):
        kind = 'DIR' if os.path.isdir(tgt) else 'FILE'
        print('[stub-skip] 已存在(%s): %s' % (kind, rel))
        return False
    d = os.path.dirname(tgt)
    try:
        if d and not os.path.isdir(d):
            try:
                os.makedirs(d, exist_ok=True)
            except FileExistsError:
                print('[stub-fail] 父路径存在但不是目录（多为符号链接被 ZIP 变成文件）: %s' % os.path.dirname(rel))
                return False
        open(tgt, 'w').write('# auto-stub: 原厂开源包中缺失，用空配置占位\n')
        print('[stub] 创建空占位: %s' % rel)
        return True
    except Exception as e:
        print('[stub-fail] %s : %s' % (rel, e))
        return False

def disable_ref(name):
    """注释掉引用 name 的 source / obj- 行"""
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
                if not s.startswith('#') and (s.startswith('source') or s.startswith('obj-') or s.startswith('subdir-') or s.startswith('ifeq')) and name in ln:
                    out.append('# auto-disabled: ' + ln)
                    ch = True; done += 1
                    print('[disable] %s : %s' % (os.path.relpath(p, ROOT), s[:88]))
                    continue
                out.append(ln)
            if ch:
                open(p, 'w', encoding='utf-8').write(''.join(out))
    return done

print('==== A: 生成 defconfig ====', flush=True)
ok = False
for i in range(1, 201):
    rc, out = run(MAKE + [DEF])
    if rc == 0:
        print('  OK（第 %d 次尝试）' % i, flush=True); ok = True; break
    m = re.search(r"can't open file \"([^\"]+)\"", out)
    if m:
        ref = m.group(1)
        if stub(ref):
            continue
        leaf = key_from_target(ref)
        if disable_ref(leaf):
            continue
        print('  !! 无法处理: %s' % ref, flush=True)
    else:
        print('  无法自动修复，末尾 20 行:', flush=True)
        for l in out.splitlines()[-20:]:
            print('   ', l[:150], flush=True)
    print('  !! 中止（第 %d 次）' % i, flush=True)
    sys.exit(3)
if not ok:
    print('  !! 超限', flush=True); sys.exit(3)

print('', flush=True)
print('==== B: 完整编译 ====', flush=True)
ok = False
for i in range(1, 201):
    rc, out = run(MAKE + ['-j%d' % (os.cpu_count() or 4)])
    if rc == 0:
        print('  编译 OK（第 %d 次尝试）' % i, flush=True); ok = True; break
    m = re.search(r"No rule to make target ['\"]([^'\"]+)['\"]", out)
    if m:
        leaf = key_from_target(m.group(1))
        print('  第 %d 次: 缺目标 %s  (关键词=%s)' % (i, m.group(1), leaf), flush=True)
        if disable_ref(leaf):
            continue
        print('  !! 找不到引用处', flush=True)
    else:
        print('  编译失败，末尾 25 行:', flush=True)
        for l in out.splitlines()[-25:]:
            print('   ', l[:150], flush=True)
    print('  !! 中止（第 %d 次）' % i, flush=True)
    sys.exit(4)
if not ok:
    print('  !! 超限', flush=True); sys.exit(4)

print('', flush=True)
print('==== 产物 ====', flush=True)
for p in ['out/arch/arm64/boot/Image.gz-dtb','out/arch/arm64/boot/Image.gz','out/arch/arm64/boot/Image']:
    fp = os.path.join(ROOT, p)
    if os.path.exists(fp):
        print('  %s (%d 字节)' % (p, os.path.getsize(fp)), flush=True)
