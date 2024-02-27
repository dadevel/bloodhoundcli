from pathlib import Path
import re
import subprocess
import sys

import click

PATTERN = re.compile(r'\$HEX\[([^]]+?)\]')


@click.group()
def hashcat() -> None:
    pass


@hashcat.command()
@click.argument('hashfile', type=click.Path(file_okay=True, dir_okay=False, path_type=Path))
@click.argument('potfile', type=click.Path(file_okay=True, dir_okay=False, path_type=Path), default=Path.home()/'.local/share/hashcat/hashcat.pot')
@click.argument('mode', type=int)
@click.argument('args', nargs=-1)
def crack(hashfile: Path, potfile: Path, mode: int, args: list[str]) -> None:
    run_hashcat(hashfile, potfile, mode, args)


@hashcat.command()
@click.argument('hashfile', type=click.Path(file_okay=True, dir_okay=False, path_type=Path))
@click.argument('potfile', type=click.Path(file_okay=True, dir_okay=False, path_type=Path), default=Path.home()/'.local/share/hashcat/hashcat.pot')
@click.argument('mode', type=int)
def show(hashfile: Path, potfile: Path, mode: int) -> None:
    process = run_hashcat(hashfile, potfile, mode, args=['--show'])
    for line in process.stdout:
        sys.stdout.write(decode_inplace(line.rstrip()))
        sys.stdout.write('\n')


def run_hashcat(hashfile: Path, potfile: Path, mode: int, args: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    command = [
        'hashcat',
        '-m', str(mode),
        '--potfile-path', potfile,
        '--restore-file-path', potfile.parent/f'{potfile.name}.restore',
        hashfile,
        *args,
    ]
    click.echo(f'runnig command: {" ".join(str(x) for x in command)}')
    return subprocess.run(command, check=False, capture_output=capture, text=True)


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
