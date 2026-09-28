#!/usr/bin/env python3
"""Build SD disk and QSPI firmware-partition images, without device access."""
import argparse
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ram_trial', Path(__file__).with_name('image-format.py'))
ram = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ram)
# Buildroot /init mounts devtmpfs before executing /sbin/init. Bypassing it
# leaves getty and services without device nodes when booting an initramfs.
BOOTARGS = ram.BOOTARGS.replace('rdinit=/bin/sh', 'rdinit=/init')
FLASH_OFFSET, FLASH_CAPACITY = 0x200000, 0x1e00000


def profile_bootargs(profile):
    if profile == 'standard':
        return BOOTARGS
    if profile == 'iq24':
        return BOOTARGS.replace('maxcpus=1', 'maxcpus=2') + ' industrialio_buffer_dma.cached_rx=1'
    raise ValueError('Unknown storage profile')


def partition_payload(fit):
    if len(fit) > FLASH_CAPACITY:
        raise ValueError('FIT exceeds the QSPI firmware partition')
    return fit + b'\xff' * (FLASH_CAPACITY - len(fit))


def verify_fit(data, expected):
    _, props, _ = ram.fdt_properties(data)
    for name, payload in expected.items():
        if props[('/images/' + name, 'data')] != payload:
            raise ValueError('FIT payload mismatch: ' + name)
        if props[('/images/' + name + '/hash@1', 'algo')] != b'sha256\0':
            raise ValueError('Wrong FIT hash algorithm')
        if props[('/images/' + name + '/hash@1', 'value')] != bytes.fromhex(ram.sha(payload)):
            raise ValueError('FIT SHA-256 mismatch: ' + name)
    for role, image in {'kernel':'linux_kernel@1', 'fdt':'fdt@1', 'ramdisk':'ramdisk@1', 'fpga':'fpga@1'}.items():
        if props[('/configurations/config@0', role)] != image.encode() + b'\0':
            raise ValueError('Wrong FIT configuration reference')
    if props[('/configurations', 'default')] != b'config@0\0':
        raise ValueError('Wrong FIT default')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ram-package', 'boot-bin', 'tools', 'dtc', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--profile', choices=('standard', 'iq24'), default='standard')
    parser.add_argument('--input-manifest', type=Path,
                        required=True,
                        help='Explicit input hashes; alternate manifests are experimental')
    args = parser.parse_args()
    bootargs = profile_bootargs(args.profile)
    if args.output.exists():
        parser.error('Output must be a new directory')
    recorded = json.loads(args.input_manifest.read_text())
    if set(recorded['artifacts']) != {'uImage', 'rootfs.cpio.uboot', 'system_top.bit', 'zynq-e200-ram.dtb'}:
        raise ValueError('Input manifest must identify exactly the four RAM package artifacts')
    inputs = {name: ram.checked_file(args.ram_package/name, info['sha256'])
              for name, info in recorded['artifacts'].items()}
    # The historical lab build and official v0.39 BOOT.BIN have distinct hashes.
    # Public builds fetch the official artifact; neither implies boot qualification.
    boot = args.boot_bin.read_bytes()
    boot_hash = ram.sha(boot)
    if boot_hash not in {
        'b8dc0281906ac27e371d21359e5071e0db058d877acc91ca2e6f8756c8d521eb',
        'd3b30bc1bdda7872d05b976e7ec2841a40287a85272003bee1bf7d4fdae8ccb0',
    }:
        raise ValueError('Unknown E200 BOOT.BIN; review its provenance before use')
    kernel_header = ram.uimage(inputs['uImage'], 2)
    ram.uimage(inputs['rootfs.cpio.uboot'], 3)
    out = args.output; out.mkdir(parents=True)
    source = out/'source'; source.mkdir()
    evidence = out/'evidence'; evidence.mkdir()
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(kernel_header['timestamp']))
    env['PATH'] = ':'.join((str(args.tools), str(args.tools.parent/'sbin'), str(args.dtc.parent), env['PATH']))
    def run(command, log, binary=False):
        result = subprocess.run(list(map(str, command)), cwd=source, env=env, capture_output=True)
        (evidence/log).write_bytes(result.stderr if binary else result.stdout + result.stderr)
        result.check_returncode()
        return result.stdout
    (source/'trial.dtb').write_bytes(inputs['zynq-e200-ram.dtb'])
    text = run([args.dtc, '-I', 'dtb', '-O', 'dts', source/'trial.dtb'], 'dtc-decompile.log').decode()
    text += '\n&{/chosen} { bootargs = "' + bootargs + '"; };\n'
    (source/'development.dts').write_text(text)
    dtb = run([args.dtc, '-I', 'dts', '-O', 'dtb', source/'development.dts'], 'dtc-compile.log', binary=True)
    old = ram.fdt_properties(inputs['zynq-e200-ram.dtb'])
    expected = dict(old[1]); expected[('/chosen', 'bootargs')] = bootargs.encode() + b'\0'
    if ram.fdt_properties(dtb) != (old[0], expected, old[2]):
        raise ValueError('Unexpected device-tree change')
    for path in ram.DISABLED:
        if expected[(path, 'status')] != b'disabled\0':
            raise ValueError('Persistent storage unexpectedly enabled')
    payloads = {'linux_kernel@1': inputs['uImage'][64:], 'fdt@1': dtb,
                'ramdisk@1': inputs['rootfs.cpio.uboot'][64:], 'fpga@1': inputs['system_top.bit']}
    if payloads['linux_kernel@1'][36:40] != bytes.fromhex('18286f01'):
        raise ValueError('Not an ARM zImage')
    if not gzip.decompress(payloads['ramdisk@1']).startswith(b'070701'):
        raise ValueError('Not a gzip CPIO ramdisk')
    image_types = {'linux_kernel@1':'kernel', 'fdt@1':'flat_dt', 'ramdisk@1':'ramdisk', 'fpga@1':'fpga'}
    nodes = []
    for name, data in payloads.items():
        filename = name.replace('@', '-') + '.bin'; (source/filename).write_bytes(data)
        extra = ''
        if name == 'linux_kernel@1': extra = 'os = "linux"; load = <0x8000>; entry = <0x8000>;'
        if name == 'fpga@1': extra = 'load = <0x0f000000>;'
        if name == 'ramdisk@1': extra = 'os = "linux";'
        compression = 'gzip' if name == 'ramdisk@1' else 'none'
        nodes.append(f'''{name} {{ description = "E200 {image_types[name]}";
            data = /incbin/("{filename}"); type = "{image_types[name]}";
            arch = "arm"; compression = "{compression}"; {extra}
            hash@1 {{ algo = "sha256"; }}; }};''')
    description = json.dumps('E200 experimental: ' + recorded.get('profile', 'recorded inputs'))
    its = '''/dts-v1/;
/ { description = ''' + description + ''';
    #address-cells = <1>;
    images { ''' + '\n'.join(nodes) + ''' };
    configurations { default = "config@0";
        config@0 { description = "E200 single RX development; boot untested";
            kernel = "linux_kernel@1"; fdt = "fdt@1";
            ramdisk = "ramdisk@1"; fpga = "fpga@1"; };
    };
};
'''
    (source/'e200.its').write_text(its)
    # Use the recorded kernel DTC explicitly, then populate FIT hashes/timestamp.
    compiled = run([args.dtc, '-I', 'dts', '-O', 'dtb', '-p', '4096', source/'e200.its'], 'dtc-fit.log', binary=True)
    (out/'e200-qspi.itb').write_bytes(compiled)
    run([args.tools/'mkimage', '-F', out/'e200-qspi.itb'], 'mkimage.log')
    fit = (out/'e200-qspi.itb').read_bytes(); verify_fit(fit, payloads)
    partition = partition_payload(fit); (out/'e200-qspi-linux.bin').write_bytes(partition)
    if partition[:len(fit)] != fit or any(x != 255 for x in partition[len(fit):]):
        raise ValueError('Bad QSPI padding')
    run([args.tools/'dumpimage', '-l', out/'e200-qspi.itb'], 'fit-inspection.log')
    sd = out/'sd-files'; sd.mkdir()
    (sd/'BOOT.bin').write_bytes(boot); (sd/'e200.itb').write_bytes(fit)
    sdboot = ('if mmcinfo && fatload mmc 0:1 0x02080000 e200.itb; '
              'then bootm 0x02080000#config@0; fi')
    sd_env = ('bootdelay=3\nbootargs=' + bootargs + '\n'
              'fdt_high=0x20000000\ninitrd_high=0x20000000\n'
              'e200_sdboot=' + sdboot + '\n'
              'bootcmd=run e200_sdboot\nsdboot=run e200_sdboot\nuenvcmd=run e200_sdboot\n')
    (sd/'uEnv.txt').write_text(sd_env)
    # This is an importable recipe, NOT a binary environment replacement or installer.
    qspi_env = ('bootdelay=3\nbootargs=' + bootargs + '\n'
                'fdt_high=0x20000000\ninitrd_high=0x20000000\n'
                'e200_qspiboot=if sf probe 0:0 50000000 0 && '
                f'sf read 0x02080000 0x{FLASH_OFFSET:x} 0x{len(fit):x}; '
                'then bootm 0x02080000#config@0; fi\n'
                'bootcmd=run e200_qspiboot\n')
    (out/'qspi-boot.env').write_text(qspi_env)
    for commands in (sd_env, qspi_env):
        for forbidden in ('saveenv', 'env save', 'sf update', 'sf write', 'sf erase', 'adi_loadvals', 'envversion', 'loaddfu'):
            if forbidden in commands: raise ValueError('Unexpected persistent operation')
    genconfig = '''image boot.vfat {
  vfat { extraargs = "-F 32 -i 45323030 -n E200BOOT"
    files = { "BOOT.bin", "e200.itb", "uEnv.txt" }
  }
  size = 128M
}
image e200-sd.img {
  hdimage { partition-table-type = "mbr" disk-signature = 0x45323030 }
  partition boot { partition-type = 0x0c bootable = "true" offset = 1M image = "boot.vfat" }
}
'''
    (source/'genimage.cfg').write_text(genconfig)
    empty = out/'empty-root'; empty.mkdir()
    generated = out/'generated'; generated.mkdir()
    run([args.tools/'genimage', '--config', source/'genimage.cfg', '--rootpath', empty,
         '--inputpath', sd, '--outputpath', generated, '--tmppath', out/'genimage-tmp'], 'genimage.log')
    disk = generated/'e200-sd.img'
    with disk.open('rb') as f: mbr = f.read(512)
    if mbr[510:512] != b'\x55\xaa' or mbr[446] != 0x80 or mbr[450] != 0x0c:
        raise ValueError('Invalid SD MBR')
    start, sectors = struct.unpack_from('<II', mbr, 454)
    if (start, sectors) != (2048, 128*1024*1024//512) or disk.stat().st_size < (start+sectors)*512:
        raise ValueError('Invalid SD partition bounds')
    extracted = evidence/'fat-readback'; extracted.mkdir()
    for name in ('BOOT.bin', 'e200.itb', 'uEnv.txt'):
        run([args.tools/'mcopy', '-i', str(disk)+'@@1048576', '::/'+name, extracted/name], 'readback-'+name+'.log')
        if (extracted/name).read_bytes() != (sd/name).read_bytes():
            raise ValueError('SD readback mismatch: ' + name)
    run([args.tools/'mdir', '-i', str(disk)+'@@1048576', '::/'], 'fat-directory.log')
    run([args.tools.parent/'sbin/fsck.fat', '-n', generated/'boot.vfat'], 'fat-check.log')
    shutil.move(disk, out/'e200-sd.img')
    # Keep the deliverables and evidence, not duplicate FAT/payload readback copies.
    shutil.rmtree(extracted); shutil.rmtree(generated)
    artifacts = {}
    for name in ('e200-sd.img', 'e200-qspi.itb', 'e200-qspi-linux.bin', 'qspi-boot.env'):
        data = (out/name).read_bytes()
        artifacts[name] = {'bytes': len(data), 'sha256': ram.sha(data)}
    manifest = {'status':'IMAGE STRUCTURE CHECK PASS; BOARD BOOT UNTESTED',
        'hardware_validated':False, 'profile':args.profile, 'bootargs':bootargs,
        'kernel_storage_controllers':'QSPI, SD0 and SD1 disabled; rootfs lives in RAM',
        'qspi':{'flash_bytes':0x2000000,'offset':FLASH_OFFSET,'partition_bytes':FLASH_CAPACITY,
                'fit_bytes':len(fit),'preserve_range':'0x000000-0x1fffff',
                'boot_recipe':'qspi-boot.env; requires live review/import; not automatically installed'},
        'sd':{'partition_start_sector':start,'partition_sectors':sectors,'partition_type':'FAT32 LBA',
              'boot_bin_sha256':boot_hash,'boot_bin_status':'pinned E200 boot artifact; this image boot untested'},
        'inputs':{name:ram.sha(data) for name,data in inputs.items()},
        'input_manifest_sha256':ram.sha(args.input_manifest.read_bytes()),
        'input_profile':recorded.get('profile', 'unspecified experimental inputs'),
        'packager_sha256':ram.sha(Path(__file__).read_bytes()),
        'checks':['input hashes','uImage CRCs','gzip CPIO','exact DT property comparison',
                  'FIT payloads, SHA256 and references','QSPI size and erased padding',
                  'MBR bounds','FAT file readback','FAT integrity','no update commands'],
        'artifacts':artifacts}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (out/'SHA256SUMS').write_text(''.join(f'{v["sha256"]}  {k}\n' for k,v in artifacts.items()))
    shutil.copy2(ROOT/'docs/release-build.md',out/'README.md')
    print(json.dumps(manifest,indent=2))


if __name__ == '__main__': main()
