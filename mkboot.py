#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
替换 Android boot.img（header v1/v2）里的 kernel 段，其余段原样保留。
零依赖，不需要 magiskboot。

用法：
    python3 mkboot.py <原始 boot.img> <新内核镜像(Image.gz)> <输出 boot.img>

为什么不用 magiskboot：
    实测从 GitHub releases 取 Magisk.apk 会失败（只拿到 9 字节），
    而 boot header v2 的结构完全可以自己解析，更可控。
"""
import hashlib
import struct
import sys

ANDROID_MAGIC = b'ANDROID!'


def parse(b):
    if bytes(b[:8]) != ANDROID_MAGIC:
        raise SystemExit('不是 Android boot image（magic 不对）：%r' % bytes(b[:8]))
    f = struct.unpack('<10I', b[8:48])
    d = {
        'kernel_size': f[0], 'kernel_addr': f[1],
        'ramdisk_size': f[2], 'ramdisk_addr': f[3],
        'second_size': f[4], 'second_addr': f[5],
        'tags_addr': f[6], 'page_size': f[7],
        'header_version': f[8], 'os_version': f[9],
    }
    if d['header_version'] >= 1:
        d['recovery_dtbo_size'], d['recovery_dtbo_offset'], d['header_size'] = \
            struct.unpack('<IQI', b[1632:1648])
    else:
        d['recovery_dtbo_size'], d['recovery_dtbo_offset'], d['header_size'] = 0, 0, 0
    if d['header_version'] >= 2:
        d['dtb_size'], d['dtb_addr'] = struct.unpack('<IQ', b[1648:1660])
    else:
        d['dtb_size'], d['dtb_addr'] = 0, 0
    return d


def pad(x, ps):
    return (x + ps - 1) // ps * ps


def layout(d):
    """返回各段在原镜像里的偏移。"""
    ps = d['page_size']
    o_k = pad(d['header_size'], ps)
    o_r = o_k + pad(d['kernel_size'], ps)
    o_s = o_r + pad(d['ramdisk_size'], ps)
    o_rec = o_s + pad(d['second_size'], ps)
    o_dtb = o_rec + pad(d['recovery_dtbo_size'], ps)
    o_end = o_dtb + pad(d['dtb_size'], ps)
    return dict(page_size=ps, kernel=o_k, ramdisk=o_r, second=o_s,
                recdtbo=o_rec, dtb=o_dtb, end=o_end)


def repack(src, newkernel, out):
    orig = bytearray(open(src, 'rb').read())
    d = parse(orig)
    lo = layout(d)
    ps = lo['page_size']
    hsz = d['header_size']

    ks, rs, ss = d['kernel_size'], d['ramdisk_size'], d['second_size']
    rec, dtbs = d['recovery_dtbo_size'], d['dtb_size']

    kernel = open(newkernel, 'rb').read()
    ramdisk = bytes(orig[lo['ramdisk']:lo['ramdisk'] + rs])
    second = bytes(orig[lo['second']:lo['second'] + ss])
    recdtbo = bytes(orig[lo['recdtbo']:lo['recdtbo'] + rec])
    dtb = bytes(orig[lo['dtb']:lo['dtb'] + dtbs])

    nks = len(kernel)

    # --- 改 header ---
    hdr = bytearray(orig[:hsz])
    struct.pack_into('<I', hdr, 8, nks)                 # kernel_size

    # id = SHA1(kernel|size|ramdisk|size|second|size[|dtb|size])，AOSP mkbootimg 口径
    sha = hashlib.sha1()
    sha.update(kernel)
    sha.update(struct.pack('<I', nks))
    sha.update(ramdisk)
    sha.update(struct.pack('<I', rs))
    sha.update(second)
    sha.update(struct.pack('<I', ss))
    if d['header_version'] >= 2:
        sha.update(dtb)
        sha.update(struct.pack('<I', dtbs))
    hdr[576:608] = sha.digest()

    # --- 拼装 ---
    img = bytearray()
    img += hdr
    img += b'\x00' * (pad(hsz, ps) - hsz)
    img += kernel
    img += b'\x00' * (pad(nks, ps) - nks)
    img += ramdisk
    img += b'\x00' * (pad(rs, ps) - rs)
    if ss:
        img += second
        img += b'\x00' * (pad(ss, ps) - ss)
    if rec:
        img += recdtbo
        img += b'\x00' * (pad(rec, ps) - rec)
    if dtbs:
        img += dtb
        img += b'\x00' * (pad(dtbs, ps) - dtbs)

    # 尾部（空洞 + AVB footer 等）：能沿用就沿用，保持总大小不变
    if len(img) <= len(orig):
        img += orig[len(img):]
    else:
        print('!! 新镜像比原镜像大 %d 字节，用 0 补齐（分区写入需注意）' % (len(img) - len(orig)))
        img += b'\x00' * (len(img) - len(orig))

    open(out, 'wb').write(img)

    print('段偏移    : kernel=%d ramdisk=%d second=%d recdtbo=%d dtb=%d end=%d'
          % (lo['kernel'], lo['ramdisk'], lo['second'], lo['recdtbo'], lo['dtb'], lo['end']))
    print('kernel 段 : %d -> %d 字节' % (ks, nks))
    print('ramdisk   : %d 字节（原样保留）' % rs)
    print('dtb 段    : %d 字节（原样保留，含 MTK 64 字节头）' % dtbs)
    print('镜像大小  : %d -> %d 字节' % (len(orig), len(img)))
    print('新 id     : %s' % sha.hexdigest())


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('用法: mkboot.py <原boot.img> <新内核> <输出boot.img>')
    repack(sys.argv[1], sys.argv[2], sys.argv[3])
