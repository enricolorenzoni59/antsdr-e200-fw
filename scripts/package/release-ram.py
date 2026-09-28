#!/usr/bin/env python3
"""Assemble newly built inputs; structural validity is not hardware qualification."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ram', Path(__file__).with_name('image-format.py'))
ram = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ram)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('kernel', 'rootfs', 'fpga', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    boot = a.kernel / 'arch/arm/boot'
    original = (boot / 'dts/xilinx/zynq-e200.dtb').read_bytes()
    baseline = json.loads((ROOT / 'configs/board.lock.json').read_text())
    if ram.sha(original) != baseline['dtb_sha256']:
        raise ValueError('Hardware description changed; review required')
    fpga = ram.checked_file(a.fpga, 'c73eb2787b0afbe8af1081be4cd4ff6d676789e91dd8f3fdd83158f58f86d423')
    data = {'uImage': (boot / 'uImage').read_bytes(),
            'rootfs.cpio.uboot': (a.rootfs / 'rootfs.cpio.uboot').read_bytes(),
            'system_top.bit': fpga}
    header = ram.uimage(data['uImage'], 2)
    ram.uimage(data['rootfs.cpio.uboot'], 3)
    if (header['load_address'], header['entry']) != ('0x8000', '0x8000'):
        raise ValueError('Unexpected kernel execution address')
    if data['uImage'][64:] != (boot / 'zImage').read_bytes():
        raise ValueError('Kernel wrapper mismatch')
    if data['rootfs.cpio.uboot'][64:] != (a.rootfs / 'rootfs.cpio.gz').read_bytes():
        raise ValueError('Rootfs wrapper mismatch')
    text = subprocess.check_output(['dtc', '-I', 'dtb', '-O', 'dts'], input=original).decode()
    for path in ram.DISABLED:
        text += '\n&{' + path + '} { status = "disabled"; };\n'
    text += '\n&{/chosen} { bootargs = "' + ram.BOOTARGS + '"; };\n'
    dtb = subprocess.check_output(['dtc', '-I', 'dts', '-O', 'dtb'], input=text.encode())
    nodes, props, reservations = ram.fdt_properties(original)
    for path in ram.DISABLED:
        props[(path, 'status')] = b'disabled\0'
    props[('/chosen', 'bootargs')] = ram.BOOTARGS.encode() + b'\0'
    if ram.fdt_properties(dtb) != (nodes, props, reservations):
        raise ValueError('Unexpected DT changes')
    data['zynq-e200-ram.dtb'] = dtb
    ram.check_ranges(data)
    a.output.mkdir(parents=True, exist_ok=False)
    for name, payload in data.items():
        (a.output / name).write_bytes(payload)
    manifest = {'status': 'BUILT; HARDWARE UNTESTED', 'hardware_validated': False,
                'profile': 'E200 single RX; Linux 6.12.111; BR2026.08 SDK14 Bash; iiod1; I16/Q16',
                'artifacts': {name: {'sha256': ram.sha(payload), 'bytes': len(payload)}
                              for name, payload in data.items()}}
    (a.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
