#!/usr/bin/env python3
"""uImage/FDT integrity and staging-range checks for the SD packager."""
import hashlib
import struct
import zlib

BOOTARGS = ('console=ttyPS0,115200 maxcpus=1 root=/dev/ram0 rw '
            'rootfstype=ramfs rdinit=/bin/sh clk_ignore_unused panic=0')
DISABLED = ('/axi/spi@e000d000', '/axi/mmc@e0100000', '/axi/mmc@e0101000')
ADDRESSES = {'system_top.bit': 0x00100000, 'zynq-e200-ram.dtb': 0x02000000,
             'uImage': 0x02080000, 'rootfs.cpio.uboot': 0x04000000}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_file(path, expected):
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError(f'Unvalidated input: {path}')
    return data


def uimage(data, image_type):
    if len(data) < 64:
        raise ValueError('Truncated uImage')
    magic, hcrc, timestamp, size, load, entry, dcrc, osid, arch, kind, comp, name = struct.unpack('>7I4B32s', data[:64])
    header = data[:4] + bytes(4) + data[8:64]
    if (magic != 0x27051956 or zlib.crc32(header) != hcrc or
            len(data) != size + 64 or zlib.crc32(data[64:]) != dcrc or
            (osid, arch, kind, comp) != (5, 2, image_type, 0)):
        raise ValueError('Invalid uImage header, type or CRC')
    return {'payload_bytes': size, 'load_address': hex(load), 'entry': hex(entry),
            'timestamp': timestamp, 'name': name.rstrip(b'\0').decode()}


def fdt_properties(data):
    """Read properties and reservations for an exact semantic before/after check."""
    if len(data) < 40:
        raise ValueError('Truncated FDT')
    magic, total, off, strings, reserve, version, _, _, strsize, size = struct.unpack('>10I', data[:40])
    if magic != 0xd00dfeed or total != len(data) or version < 17:
        raise ValueError('Invalid FDT header')
    stringdata = data[strings:strings + strsize]
    props, stack, nodes = {}, [], set()
    end = off + size
    while off < end:
        token, = struct.unpack_from('>I', data, off); off += 4
        if token == 1:
            stop = data.index(b'\0', off)
            stack.append(data[off:stop].decode()); off = (stop + 4) & ~3
            nodes.add('/'.join(stack) or '/')
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from('>II', data, off); off += 8
            name = stringdata[nameoff:stringdata.index(b'\0', nameoff)].decode()
            key = ('/'.join(stack) or '/', name)
            if key in props:
                raise ValueError('Duplicate FDT property')
            props[key] = data[off:off + length]; off = (off + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            reservations = []
            while True:
                addr, length = struct.unpack_from('>QQ', data, reserve); reserve += 16
                if (addr, length) == (0, 0):
                    return nodes, props, reservations
                reservations.append((addr, length))
        else:
            raise ValueError('Invalid FDT token')
    raise ValueError('Missing FDT end token')


def check_ranges(artifacts):
    intervals = sorted((ADDRESSES[name], ADDRESSES[name] + len(data), name)
                       for name, data in artifacts.items())
    for start, end, name in intervals:
        # Historical board: 512 MiB; reserve everything above 256 MiB for bootloader use.
        if start < 0x100000 or end > 0x10000000:
            raise ValueError(f'Artifact outside conservative staging range: {name}')
    for left, right in zip(intervals, intervals[1:]):
        if left[1] > right[0]:
            raise ValueError(f'RAM overlap: {left[2]} and {right[2]}')
