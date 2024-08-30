from collections import defaultdict
from pathlib import Path
from typing import TextIO, TypedDict
import re
import sys

import click

from bloodhoundcli.hashcat import decode_password
from bloodhoundcli.neo4j import Database
from bloodhoundcli.util import nthash

DOMAIN_PATTERN = re.compile(r'^(?:(?:[a-z0-9-]+)\.)+(?:[a-z0-9-]+)$')


@click.command(help='Import hashes and cracked passwords from DCSync')
@click.argument('ntds', type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path), nargs=-1)
@click.option('-p', '--potfile', type=click.Path(file_okay=True, dir_okay=False, path_type=Path), default=Path.home()/'.local/share/hashcat/hashcat.potfile')
def import_ntds(ntds: list[Path], potfile: Path) -> None:
    neo4j = Database.from_env()
    neo4j.create_indices()

    with open(potfile, 'r') as file:
        potdb = parse_potfile(file)
    print(f'loaded {len(potdb)} cracked hashes from {potfile}', file=sys.stderr)

    for path in ntds:
        if not path.suffix == '.ntds':
            print(f'warning: skipping {path} with unknown file format')
        domain = path.name.removesuffix('.ntds')
        if not DOMAIN_PATTERN.fullmatch(domain):
            raise RuntimeError(f'{path} does not follow the expected naming scheme, a DCSync from the corp.local domain should be named corp.local.ntds')

        path_cleartext = Path(f'{path}.cleartext')
        if path_cleartext.exists():
            with open(path_cleartext, 'r') as file:
                cleardb = parse_ntds_cleartext(file)
            print(f'loaded {len(cleardb)} passwords for {domain} from {path_cleartext}', file=sys.stderr)
            if cleardb:
                import_ntds_cleartext(neo4j, domain, cleardb)

        with open(path, 'r') as file:
            ntdsdb = parse_ntds(file)
        print(f'loaded {len(ntdsdb)} hashes for {domain} from {path}', file=sys.stderr)
        if ntdsdb:
            import_ntds_internal(neo4j, domain, ntdsdb)
        if ntdsdb and potdb:
            import_potfile(neo4j, domain, ntdsdb, potdb)
        # TODO: import kerberos keys into neo4j


class NtdsEntry(TypedDict):
    domain: str
    user: str
    nthash: str
    lmhash: str


def import_ntds_cleartext(neo4j: Database, domain: str, cleardb: dict[str, str]) -> None:
    count = sum(neo4j.execute(
        'UNWIND $rows AS row MERGE (c:Base:Container:Credential {objectid: row[0]}) SET c.nthash=row[0], c.password=row[1], c.cracked=false, c.name=row[2] RETURN count(c)',
        rows=[
            [nthash(password), password, 'Plain Password']
            for password in cleardb.values()
        ],
    ))
    print(f'updated {count} cleartext passwords')
    count = sum(neo4j.execute(
        'UNWIND $rows AS row MATCH (c:Credential {objectid: row[0]}) MATCH (o {domain: row[1], samaccountname: row[2]}) WHERE o:User OR o:Computer MERGE (o)-[r:HasCredential]->(c) MERGE (c)-[s:AssignedTo]->(o) RETURN count(r) + count(s)',
        rows=[
            [nthash(password), domain.upper(), user]
            for user, password in cleardb.items()
        ],
    ))
    print(f'updated {count} credential relationships')


def import_ntds_internal(neo4j: Database, domain: str, ntdsdb: list[NtdsEntry]) -> None:
    # when multiple lm hashes map to the same nt hash, all except the last lm hash are lost
    # to reduce the risk the empty lm hash is filtered out
    count = sum(neo4j.execute(
        'UNWIND $rows AS row MERGE (c:Base:Container:Credential {objectid: row[0]}) SET c.nthash=row[0], c.lmhash=coalesce(c.lmhash, coalesce(row[1], c.lmhash)), c.name=row[2] RETURN count(c)',
        rows=[
            [
                entry['nthash'],
                None if entry['lmhash'] == 'aad3b435b51404eeaad3b435b51404ee' else entry['lmhash'],
                'NT Hash',
            ]
            for entry in ntdsdb
        ],
    ))
    print(f'updated {count} NT hashes')
    count = sum(neo4j.execute(
        'UNWIND $rows AS row MATCH (c:Credential {objectid: row[0]}) MATCH (o {domain: row[1], samaccountname: row[2]}) WHERE o:User OR o:Computer MERGE (o)-[r:HasCredential]->(c) MERGE (c)-[s:AssignedTo]->(o) RETURN count(r) + count(s)',
        rows=[
            [entry['nthash'], domain.upper(), entry['user']]
            for entry in ntdsdb
        ],
    ))
    print(f'updated {count} credential relationships')


def import_potfile(neo4j: Database, domain: str, ntdsdb: list[NtdsEntry], potdb: dict[str, str]) -> None:
    # TODO: import cracked lm passwords into neo4j
    count = sum(neo4j.execute(
        'UNWIND $rows AS row MERGE (c:Base:Container:Credential {objectid: row[0]}) SET c.nthash=row[0], c.password=row[1], c.cracked=true, c.name=row[2] RETURN count(c)',
        rows=[
            [entry['nthash'], potdb.get(entry['nthash']), 'Cracked NT Hash']
            for entry in ntdsdb
            if potdb.get(entry['nthash'])  # uncracked hashes are already handled by import_ntds()
        ],
    ))
    print(f'updated {count} cracked NT hashes')
    count = sum(neo4j.execute(
        'UNWIND $rows AS row MATCH (c:Credential {objectid: row[0]}) MATCH (o {domain: row[1], samaccountname: row[2]}) WHERE o:User OR o:Computer MERGE (o)-[r:HasCredential]->(c) MERGE (c)-[s:AssignedTo]->(o) RETURN count(r) + count(s)',
        rows=[
            [entry['nthash'], domain.upper(), entry['user']]
            for entry in ntdsdb
            if potdb.get(entry['nthash'])
        ],
    ))
    print(f'updated {count} credential relationships')


def parse_ntds_cleartext(file: TextIO) -> dict[str, str]:
    """Returns mapping from user to password."""
    result = {}
    pattern = re.compile(r'^(?:(?P<domain>[^\:]+?)\\)?(?P<user>[^:]+?):CLEARTEXT:(?P<password>.*?)$')
    for linenum, line in enumerate(file, start=1):
        line = line.rstrip()
        match = pattern.search(line)
        if not match:
            print(f'{file.name}:{linenum}: invalid line: {line}', file=sys.stderr)
            continue
        entry = match.groupdict()
        result[entry['user']] = entry['password']
    return result


def parse_ntds(file: TextIO) -> list[NtdsEntry]:
    """Returns mapping from nthash to NTDS entry."""
    result = []
    pattern = re.compile(r'^(?:(?P<domain>[^\:]+?)\\)?(?P<user>[^:]+?):[^:]+?:(?P<lmhash>[^:]+?):(?P<nthash>[^:]+?):')
    for linenum, line in enumerate(file, start=1):
        line = line.rstrip()
        match = pattern.search(line)
        if not match:
            print(f'{file.name}:{linenum}: invalid line: {line}', file=sys.stderr)
            continue
        entry = match.groupdict()
        result.append(entry)
    return result


def parse_potfile(file: TextIO) -> dict[str, str]:
    """Returns mapping from nthash to password."""
    pattern = re.compile(r'^([^\:]{32}?):(.*?)$')
    result = dict()
    for line in file:
        line = line.rstrip()
        match = pattern.search(line)
        if not match:
            continue
        nthash, password = match.groups()
        result[nthash] = decode_password(password)
    return result
