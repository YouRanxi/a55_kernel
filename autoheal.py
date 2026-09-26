#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动愈合不完整的内核源码树（OPPO 开源包经典问题）v3。

v3 新增：
  * 父路径"是文件不是目录"时，直接删掉那个（被 ZIP 弄坏的符号链接）文件，改建目录
  * 补头文件失败时，退而求其次：把 #include 那一行注释掉
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


def ensure_dir(d):
    """保证 d 是目录：如果是被 ZIP 弄坏的文件，删掉后建目录"""
    if os.path.isdir(d):
        return True
    if os.path.exists(d):
        try:
            os.remove(d)
            print('[fixdir] 删除被 ZIP 破坏的文件，改建目录: %s' % os.path.relpath(d, ROOT), flush=True)
        except Exception as e:
            print('[fixdir-fail] %s : %s' % (d, e), flush=True)
            return False
    try:
        os.makedirs(d, exist_ok=True)
        return True
    except Exception as e:
        print('[fixdir-fail] %s : %s' % (d, e), flush=True)
        return False


def stub_file(rel, comment):
    tgt = os.path.join(ROOT, rel)
    if os.path.exists(tgt):
        kind = 'DIR' if os.path.isdir(tgt) else 'FILE'
        print('[skip] 已存在(%s): %s' % (kind, rel), flush=True)
        return False
    d = os.path.dirname(tgt)
    if d and not ensure_dir(d):
        return False
    try:
        open(tgt, 'w').write(comment)
        print('[stub] %s' % rel, flush=True)
        return True
    except Exception as e:
        print('[stub-fail] %s : %s' % (rel, e), flush=True)
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
                    print('[disable] %s : %s' % (os.path.relpath(p, ROOT), s[:84]), flush=True)
                    continue
                out.append(ln)
            if ch:
                open(p, 'w', encoding='utf-8').write(''.join(out))
    return done


def comment_include(hdr):
    """把所有 #include <hdr> / "hdr" 注释掉"""
    done = 0
    pat = re.compile(r'^(\s*)#\s*include\s*[<"]' + re.escape(hdr) + r'[>"]')
    for dp, dn, fn in os.walk(ROOT):
        if '.git' in dp.split(os.sep):
            continue
        for f in fn:
            if not (f.endswith('.c') or f.endswith('.h') or f.endswith('.S')):
                continue
            p = os.path.join(dp, f)
            try:
                lines = open(p, encoding='utf-8', errors='replace').read().splitlines(True)
            except Exception:
                continue
            out, ch = [], False
            for ln in lines:
                if pat.match(ln):
                    out.append('// auto-disabled-include: ' + ln)
                    ch = True
                    done += 1
                    print('[noinclude] %s' % os.path.relpath(p, ROOT), flush=True)
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

    handled = False

    # 1) 缺头文件
    mh = RE_HEADER.search(out)
    if mh:
        hdr = mh.group(1)
        if stub_file(os.path.join('include', hdr),
                     '#pragma once\n/* auto-stub: 原厂开源包缺失的私有头文件 */\n'):
            print('  第 %d 次: 补空头文件 %s' % (i, hdr), flush=True)
            handled = True
        elif comment_include(hdr):
            print('  第 %d 次: 已注释掉 #include <%s>' % (i, hdr), flush=True)
            handled = True
        if handled:
            continue

    # 2) 缺目标
    m = RE_NOTARGET.search(out)
    if m:
        leaf = key_from(m.group(1))
        print('  第 %d 次: 缺目标 %s (关键词 %s)' % (i, m.group(1), leaf), flush=True)
        if disable_ref(leaf):
            continue
        print('  !! 找不到引用处', flush=True)

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
