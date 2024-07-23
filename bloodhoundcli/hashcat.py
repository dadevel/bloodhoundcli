from pathlib import Path
from tempfile import NamedTemporaryFile
import re
import subprocess
import sys

import click

from bloodhoundcli.neo4j import Database

PATTERN = re.compile(r'\$HEX\[([^]]+?)\]')


@click.command(help='Crack DCSync with multiple wordlists and rules')
@click.argument('ntds', type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path), nargs=-1)
@click.option('-p', '--potfile', type=click.Path(file_okay=True, dir_okay=False, path_type=Path), default=Path.home()/'.local/share/hashcat/hashcat.potfile')
@click.option('-t', '--task', nargs=2, multiple=True)
@click.option('--pre2k/--no-pre2k', is_flag=True, default=True)
@click.option('--lmbrute/--no-lmbrute', is_flag=True, default=True)
def hashcat_ntds(ntds: list[str], potfile: Path, task: list[tuple[str, str]], pre2k: bool, lmbrute: bool) -> None:
    if not ntds:
        exit(1)
    with NamedTemporaryFile('w', prefix='hashcat-', suffix='.txt') as userlist, NamedTemporaryFile('w', prefix='hashcat-', suffix='.txt') as lmhashes, NamedTemporaryFile('w', prefix='hashcat-', suffix='.txt') as lmpasswords,NamedTemporaryFile('w', prefix='hashcat-', suffix='.txt') as computerlist, NamedTemporaryFile('w', prefix='hashcat-', suffix='.txt') as pre2klist:
        for path in ntds:
            click.echo(f'parsing ntds {path}')
            with open(path, 'r') as input:
                for line in input:
                    identity, _, lmhash, nthash, *_ = line.split(':')
                    if identity.endswith('$'):
                        computerlist.write(nthash)
                        computerlist.write('\n')
                    else:
                        userlist.write(nthash)
                        userlist.write('\n')
                        lmhashes.write(lmhash)
                        lmhashes.write('\n')

        potfile.parent.mkdir(exist_ok=True)

        if pre2k:
            neo4j = Database.from_env()
            for name in neo4j.execute('MATCH (c:Computer {enabled: true}) WHERE c.lastlogon=0 OR c.lastlogon IS NULL RETURN toLower(c.samaccountname)'):
                if not name:
                    continue
                name = name.removesuffix('$')
                name = name[:14]
                pre2klist.write(name)
                pre2klist.write('\n')
            click.echo('cracking pre2k computer hashes')
            run_hashcat(hashfile=Path(computerlist.name), potfile=potfile, mode=1000, args=[pre2klist.name, '-O', '-w', '3', '-a', '0'])

        if lmbrute:
            click.echo('cracking user lm hashes')
            run_hashcat(hashfile=Path(lmhashes.name), potfile=potfile, mode=3000, args=['--increment', '--increment-min', '1', '-1', '?d?u !#$%*+-??@_.', '?1?1?1?1?1?1?1', '-w', '3', '-a', '3'])

            click.echo('generating password list from cracked lm hashes')
            process = run_hashcat(hashfile=Path(lmhashes.name), potfile=potfile, mode=3000, args=['--show'], capture=True)
            for line in process.stdout.splitlines():
                if line.startswith('aad3b435b51404eeaad3b435b51404ee:'):
                    continue
                _, password = line.split(':', maxsplit=1)
                lmpasswords.write(password.rstrip())
                lmpasswords.write('\n')

            click.echo('cracking user nt hashes with cracked lm hashes')
            for _, ruleset in task:
                run_hashcat(hashfile=Path(userlist.name), potfile=potfile, mode=1000, args=[lmpasswords.name, '-r', ruleset, '-O', '-w', '3', '-a', '0', '--loopback'])

        click.echo('cracking user nt hashes')
        for wordlist, ruleset in task:
            run_hashcat(hashfile=Path(userlist.name), potfile=potfile, mode=1000, args=[wordlist, '-r', ruleset, '-O', '-w', '3', '-a', '0', '--loopback'])


@click.command(help='Print cracked passwords and decode $HEX encoding')
@click.argument('hashfile', type=click.Path(file_okay=True, dir_okay=False, path_type=Path))
@click.option('-p', '--potfile', type=click.Path(file_okay=True, dir_okay=False, path_type=Path), default=Path.home()/'.local/share/hashcat/hashcat.potfile')
@click.option('--username', is_flag=True)
@click.argument('mode', type=int)
def hashcat_decode(hashfile: Path, potfile: Path, mode: int, username: bool) -> None:
    args = ['--show']
    if username:
        args.append('--username')
    process = run_hashcat(hashfile, potfile, mode, args, capture=True)
    for line in process.stdout.splitlines():
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
