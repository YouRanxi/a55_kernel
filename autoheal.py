#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动愈合不完整的内核源码树（OPPO 开源包经典问题）。

修复要点：
  * 兼容 clang 与 gcc 两种 "找不到头文件" 的报错格式
  * 只注释 source / obj- / subdir- 行，绝不碰 ifeq（否则破坏 if/else 配对）
  * 路径存在但不是目录（ZIP 把符号链接变成文件）时不崩，改走禁用引用
用法: python3 autoheal.py <kernel根目录> <defconfig名>
"""
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '.')
DEF = sys.argv[2] if len(sys.argv) > 2 else 'k6833v1_64_k419_defconfig'
MAKE = ['make', 'ARCH=arm64', 'O=out', 'CC=clang',
        'CLANG_TRIPLE=aarch64-linux-gnu-',
        'CROSS_COMPILE=aarch64-linux-gnu-',
        'CROSS_COMPILE_ARM32=arm-linux-gnueabi-']

RE_KCONFIG = re.compile(r'can\'t open file "([^"]+)"')
RE_NOTARGET = re.compile(r"No rule to make target ['\"]([^'\"]+)['\"]")
# clang:  fatal error: 'a/b.h' file not found
# gcc  :  fatal error: a/b.h: No such file or directory
RE_HEADER = re.compile(r'fatal error: [\'"]?([^\s:\'"]+\.h)[\'"]?:? (?:No such file|file not found)')


def run(args, timeout=7200):
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                       errors='replace', timeout=timeout)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def key_from(rel):
    parts = [x for x in rel.replace('\\', '/').split('/') if x and x not in ('.', '..')]
    if parts and parts[-1] in ('Makefile', 'Kbuild', 'Kconfig'):
        parts = parts[:-1]
    return parts[-1] if parts else rel


def stub_file(rel, comment):
    tgt = os.path.join(ROOT, rel)
    if os.path.exists(tgt):
        kind = 'DIR' if os.path.isdir(tgt) else 'FILE'
        print('[skip] 已存在(%s): %s' % (kind, rel), flush=True)
        return False
    d = os.path.dirname(tgt)
    try:
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        open(tgt, 'w').write(comment)
        print('[stub] %s' % rel, flush=True)
        return True
    except FileExistsError:
        print('[fail] 父路径不是目录（符号链接被 ZIP 变成文件）: %s' % d, flush=True)
        return False
    except Exception as e:
        print('[fail] %s : %s' % (rel, e), flush=True)
        return False


def disable_ref(name):
    done = 0
    for dp, dn, fn in os.walk(ROOT):
        if '.git' in dp.split(os.sep):
            continue
        for f in fn:
            if f not in ('Makefile', 'Kbuild') and not f.startswith('Kconfig'):
                continue
            p = os.path.join(dp, f)
            try:
                lines = open(p, encoding='utf-8', errors='replace').read().splitlines(True)
            except Exception:
                continue
            out, ch = [], False
            for ln in lines:
                s = ln.strip()
                if (not s.startswith('#')
                        and (s.startswith('source') or s.startswith('obj-') or s.startswith('subdir-'))
                        and name in ln):
                    out.append('# auto-disabled: ' + ln)
                    ch = True
                    done += 1
                    print('[disable] %s : %s' % (os.path.relpath(p, ROOT), s[:86]), flush=True)
                    continue
                out.append(ln)
            if ch:
                open(p, 'w', encoding='utf-8').write(''.join(out))
    return done


print('==== A: 生成 defconfig ====', flush=True)
ok = False
for i in range(1, 401):
    rc, out = run(MAKE + [DEF])
    if rc == 0:
        print('  OK（第 %d 次）' % i, flush=True)
        ok = True
        break
    m = RE_KCONFIG.search(out)
    if m:
        ref = m.group(1)
        if stub_file(ref, '# auto-stub: 原厂开源包缺失，用空配置占位\n'):
            continue
        if disable_ref(key_from(ref)):
            continue
        print('  !! 无法处理 %s' % ref, flush=True)
    else:
        print('  无法自动修复，末尾 20 行:', flush=True)
        for l in out.splitlines()[-20:]:
            print('   ', l[:150], flush=True)
    print('  !! 中止（第 %d 次）' % i, flush=True)
    sys.exit(3)
if not ok:
    print('  !! 超限', flush=True)
    sys.exit(3)

print('', flush=True)
print('==== B: 完整编译 ====', flush=True)
ok = False
for i in range(1, 401):
    rc, out = run(MAKE + ['-j%d' % (os.cpu_count() or 4)])
    if rc == 0:
        print('  编译 OK（第 %d 次）' % i, flush=True)
        ok = True
        break

    mh = RE_HEADER.search(out)
    if mh:
        hdr = mh.group(1)
        if stub_file(os.path.join('include', hdr),
                     '#pragma once\n/* auto-stub: 原厂开源包缺失的私有头文件 */\n'):
            print('  第 %d 次: 补空头文件 %s' % (i, hdr), flush=True)
            continue
        print('  第 %d 次: 头文件 %s 存在却仍缺失' % (i, hdr), flush=True)

    m = RE_NOTARGET.search(out)
    if m:
        leaf = key_from(m.group(1))
        print('  第 %d 次: 缺目标 %s (关键词 %s)' % (i, m.group(1), leaf), flush=True)
        if disable_ref(leaf):
            continue
        print('  !! 找不到引用处', flush=True)
        print('  末尾 20 行:', flush=True)
        for l in out.splitlines()[-20:]:
            print('   ', l[:150], flush=True)
        sys.exit(4)

    print('  编译失败且无法自动修复，末尾 25 行:', flush=True)
    for l in out.splitlines()[-25:]:
        print('   ', l[:150], flush=True)
    print('  !! 中止（第 %d 次）' % i, flush=True)
    sys.exit(4)

if not ok:
    print('  !! 超限', flush=True)
    sys.exit(4)

print('', flush=True)
print('==== 产物 ====', flush=True)
for p in ['out/arch/arm64/boot/Image.gz-dtb', 'out/arch/arm64/boot/Image.gz',
          'out/arch/arm64/boot/Image']:
    fp = os.path.join(ROOT, p)
    if os.path.exists(fp):
        print('  %s (%d 字节)' % (p, os.path.getsize(fp)), flush=True)
