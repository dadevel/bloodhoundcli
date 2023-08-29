from collections import defaultdict
from typing import TextIO
import re
import sys

import click

from bloodhoundcli.hashcat import run_hashcat, decode_password
from bloodhoundcli.db import execute, find_shared_passwords


@click.group()
def ntds() -> None:
    pass


@ntds.command()
@click.argument('ntds')
@click.option('-t', '--task', nargs=2, multiple=True)
@click.option('--keep-computers', is_flag=True)
def crack(ntds: str, task: list[tuple[str, str]], keep_computers: bool) -> None:
    with open(ntds, 'r') as input:
        with open(f'{ntds}.users', 'w') as userlist, open(f'{ntds}.computers', 'w') as computerlist:
            for line in input:
                identity, _ = line.split(':', maxsplit=1)
                if identity.endswith('$'):
                    computerlist.write(line)
                else:
                    userlist.write(line)
    for wordlist, ruleset in task:
        run_hashcat(1000, ntds if keep_computers else f'{ntds}.users', wordlist, '-r', ruleset, '-O', '-w', '3', '-a', '0', '--loopback')


@ntds.command('import')
@click.option('-n', '--ntds')
@click.option('-c', '--ntds-cleartext')
@click.option('-p', '--potfile')
def import_(ntds: str, ntds_cleartext: str, potfile: str) -> None:
    if ntds_cleartext:
        with open(ntds_cleartext, 'r') as file:
            cleardb = parse_ntds_cleartext(file)
            print(f'loaded {len(cleardb)} passwords from cleartext ntds', file=sys.stderr)
    else:
        cleardb = None

    if ntds:
        with open(ntds, 'r') as file:
            ntdsdb = parse_ntds(file)
            print(f'loaded {len(ntdsdb)} hashes from ntds', file=sys.stderr)
    else:
        ntdsdb = None

    if potfile:
        with open(potfile, 'r') as file:
            potdb = parse_potfile(file)
            print(f'loaded {len(potdb)} cracked passwords from potfile', file=sys.stderr)
    else:
        potdb = None

    if cleardb:
        import_ntds_cleartext(cleardb)
    if ntdsdb:
        import_ntds(ntdsdb)
    if ntdsdb and potdb:
        import_potfile(ntdsdb, potdb)

    find_shared_passwords()


def import_ntds_cleartext(cleardb) -> None:
    count = sum(execute(
        'UNWIND $rows AS row MATCH (u:User {samaccountname: row[0]}) SET u.cracked=false, u.password=row[1] RETURN count(u)',
        rows=[
            [user, password]
            for user, password in cleardb.items()
        ],
    ))
    print(f'updated clear text passwords of {count} users')


def import_ntds(ntdsdb) -> None:
    count = sum(execute(
        'UNWIND $rows AS row MATCH (u:User {samaccountname: row[0]}) SET u.nthash=row[1] RETURN count(u)',
        rows=[
            [entry['user'], entry['nthash']]
            for entries in ntdsdb.values()
            for entry in entries
        ],
    ))
    print(f'updated hashes of {count} users')


def import_potfile(ntdsdb, potdb) -> None:
    count = sum(execute(
        'UNWIND $rows AS row MATCH (u:User {samaccountname: row[0]}) SET u.cracked=true, u.password=row[1] RETURN count(u)',
        rows=[
            [entry['user'], password]
            for nthash, password in potdb.items()
            for entry in ntdsdb[nthash]
        ],
    ))
    print(f'updated cracked passwords of {count} users')


def parse_ntds_cleartext(file: TextIO) -> dict[str, str]:
    result = {}
    pattern = re.compile(r'^(?:(?P<domain>[^\:]+?)\\)?(?P<user>[^:]+?):CLEARTEXT:(?P<password>.*?)$')
    for line in file:
        line = line.rstrip()
        match = pattern.search(line)
        if not match:
            print(f'ingonring invalid line: {line}', file=sys.stderr)
            continue
        entry = match.groupdict()
        result[entry['user']] = entry['password']
    return result


def parse_ntds(file: TextIO) -> dict[str, list[dict[str, str]]]:
    result = defaultdict(list)
    pattern = re.compile(r'^(?:(?P<domain>[^\:]+?)\\)?(?P<user>[^:]+?):[^:]+?:[^:]+?:(?P<nthash>[^:]+?):')
    for line in file:
        line = line.rstrip()
        match = pattern.search(line)
        if not match:
            print(f'ingonring invalid line: {line}', file=sys.stderr)
            continue
        entry = match.groupdict()
        result[entry['nthash']].append(entry)
    return result


def parse_potfile(file: TextIO) -> dict[str, str]:
    pattern = re.compile(r'^([^\:]+?):(.*?)$')
    result = dict()
    for line in file:
        line = line.rstrip()
        match = pattern.search(line)
        if not match:
            print(f'ingonring invalid line: {line}', file=sys.stderr)
        assert match
        nthash, password = match.groups()
        result[nthash] = decode_password(password)
    return result
