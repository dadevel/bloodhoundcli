import re
import subprocess
import sys

import click

PATTERN = re.compile(r'\$HEX\[([^]]+?)\]')


@click.group()
def hashcat() -> None:
    pass


@hashcat.command()
@click.argument('mode', type=int)
@click.argument('hashfile')
@click.argument('args', nargs=-1)
def crack(mode: int, hashfile: str, args: str) -> None:
    run_hashcat(mode, hashfile, *args)


def run_hashcat(mode: int, hashfile: str, *args: str, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            'hashcat',
            '-m', str(mode),
            '--potfile-path', f'{hashfile}.potfile',
            '--restore-file-path', f'{hashfile}.restore',
            hashfile,
            *args,
        ],
        check=False,
        capture_output=capture,
        text=True,
    )


@hashcat.command()
def decode() -> None:
    for line in sys.stdin:
        sys.stdout.write(decode_inplace(line.rstrip()))
        sys.stdout.write('\n')


def decode_inplace(line: str) -> str:
    return PATTERN.sub(lambda m: decode_hex(m.group(1)), line)


def decode_password(value: str) -> str:
    match = PATTERN.search(value)
    if not match:
        return value
    return decode_hex(match.group(1))


def decode_hex(hexdata: str) -> str:
    bindata = bytes.fromhex(hexdata)
    try:
        return bindata.decode('cp1252')
    except Exception:
        return bindata.decode()
