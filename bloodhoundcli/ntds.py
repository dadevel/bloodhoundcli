from pathlib import Path
from typing import TextIO, TypedDict
import re
import sys

import click

from bloodhoundcli.hashcat import decode_password
from bloodhoundcli.neo4j import Database

DOMAIN_PATTERN = re.compile(r'^(?:(?:[a-z0-9-]+)\.)+(?:[a-z0-9-]+)$')
EMPTY_LMHASH = 'aad3b435b51404eeaad3b435b51404ee'
DISABLED_NTHASH = '31d6cfe0d16ae931b73c59d7e0c089c0'


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

        with open(path, 'r') as file:
            ntdsdb = parse_ntds(file)
        print(f'loaded {len(ntdsdb)} hashes for {domain} from {path}', file=sys.stderr)

        path_cleartext = Path(f'{path}.cleartext')
        if path_cleartext.exists():
            with open(path_cleartext, 'r') as file:
                cleardb = parse_ntds_cleartext(file)
            print(f'loaded {len(cleardb)} passwords for {domain} from {path_cleartext}', file=sys.stderr)
        else:
            cleardb = None

        if ntdsdb:
            import_ntds_internal(neo4j, domain, ntdsdb)
        # clear text passwords must be imported before potfile, because it sets the 'cracked' attribute to 'false'
        if cleardb:
            import_ntds_cleartext(neo4j, domain, ntdsdb, cleardb)
        if ntdsdb and potdb:
            import_potfile(neo4j, domain, ntdsdb, potdb)
        # TODO: import kerberos keys into neo4j


class NtdsEntry(TypedDict):
    longname: str
    rid: str
    nthash: str
    lmhash: str


def import_ntds_internal(neo4j: Database, domain: str, ntdsdb: dict[str, NtdsEntry]) -> None:
    # when multiple lm hashes map to the same nt hash, all except the last lm hash are lost
    # to reduce the risk the empty lm hash is filtered out
    count = sum(neo4j.execute(
        'UNWIND $rows AS row MERGE (c:Base:Container:Credential {objectid: row[0]}) SET c.nthash=row[0], c.lmhash=coalesce(c.lmhash, coalesce(row[1], c.lmhash)), c.name=row[2] RETURN count(c)',
        rows=[
            [
                entry['nthash'],
                None if entry['lmhash'] == EMPTY_LMHASH else entry['lmhash'],
                'NT Hash',
            ]
            for entry in ntdsdb.values()
        ],
    ))
    print(f'updated {count} NT hashes')

    # the mapping is performed by rid instead of by samaccountname, because in some weird scenarios the latter is not unique
    # see https://github.com/dadevel/bloodhoundcli/issues/9
    count = sum(neo4j.execute(
        'UNWIND $rows AS row MATCH (c:Credential {objectid: row[0]}) MATCH (o {domain: row[1]}) WHERE (o:User OR o:Computer) AND o.objectid ENDS WITH ("-" + row[2]) MERGE (o)-[r:HasCredential]->(c) MERGE (c)-[s:AssignedTo]->(o) RETURN count(r) + count(s)',
        rows=[
            [entry['nthash'], domain.upper(), entry['rid']]
            for entry in ntdsdb.values()
        ],
    ))
    print(f'updated {count} credential relationships')


def import_ntds_cleartext(neo4j: Database, domain: str, ntdsdb: dict[str, NtdsEntry], cleardb: dict[str, str]) -> None:
    count = sum(neo4j.execute(
        'UNWIND $rows AS row MERGE (c:Base:Container:Credential {objectid: row[0]}) SET c.nthash=row[0], c.password=row[1], c.cracked=false, c.name=row[2] RETURN count(c)',
        rows=[
            [entry['nthash'], password, 'Plain Password']
            for entry in ntdsdb.values()
            if (password := cleardb.get(entry['longname']))
        ],
    ))
    print(f'updated {count} cleartext passwords')

    count = sum(neo4j.execute(
        'UNWIND $rows AS row MATCH (c:Credential {objectid: row[0]}) MATCH (o {domain: row[1]}) WHERE (o:User OR o:Computer) AND o.objectid ENDS WITH ("-" + row[2]) MERGE (o)-[r:HasCredential]->(c) MERGE (c)-[s:AssignedTo]->(o) RETURN count(r) + count(s)',
        rows=[
            [entry['nthash'], domain.upper(), entry['rid']]
            for entry in ntdsdb.values()
            if cleardb.get(entry['longname'])
        ],
    ))
    print(f'updated {count} credential relationships')


def import_potfile(neo4j: Database, domain: str, ntdsdb: dict[str, NtdsEntry], potdb: dict[str, str]) -> None:
    # TODO: import cracked lm passwords into neo4j
    count = sum(neo4j.execute(
        'UNWIND $rows AS row MERGE (c:Base:Container:Credential {objectid: row[0]}) SET c.nthash=row[0], c.password=row[1], c.cracked=true, c.name=row[2] RETURN count(c)',
        rows=[
            [entry['nthash'], password, 'Cracked NT Hash']
            for entry in ntdsdb.values()
            if (password := potdb.get(entry['nthash']))  # uncracked hashes are already handled by import_ntds()
        ],
    ))
    print(f'updated {count} cracked NT hashes')

    count = sum(neo4j.execute(
        'UNWIND $rows AS row MATCH (c:Credential {objectid: row[0]}) MATCH (o {domain: row[1]}) WHERE (o:User OR o:Computer) AND o.objectid ENDS WITH ("-" + row[2]) MERGE (o)-[r:HasCredential]->(c) MERGE (c)-[s:AssignedTo]->(o) RETURN count(r) + count(s)',
        rows=[
            [entry['nthash'], domain.upper(), entry['rid']]
            for entry in ntdsdb.values()
            if potdb.get(entry['nthash'])
        ],
    ))
    print(f'updated {count} credential relationships')


def parse_ntds_cleartext(file: TextIO) -> dict[str, str]:
    """Returns mapping from domain\\samaccountname to password."""
    result = {}
    # format: corp.local\administrator:CLEARTEXT:passw0rd
    pattern = re.compile(r'^(?P<longname>[^:]+?):CLEARTEXT:(?P<password>.*?)$')
    for linenum, line in enumerate(file, start=1):
        line = line.rstrip()
        match = pattern.search(line)
        if not match:
            print(f'{file.name}:{linenum}: invalid line: {line}', file=sys.stderr)
            continue
        entry = match.groupdict()
        result[entry['longname']] = entry['password']
    return result


def parse_ntds(file: TextIO) -> dict[str, NtdsEntry]:
    """Returns mapping from domain\\samaccountname to NTDS entry."""
    result = {}
    # format: corp.local\administrator:500:aad3b435b51404eeaad3b435b51404ee:b9f917853e3dbf6e6831ecce60725930:...
    pattern = re.compile(r'^(?P<longname>[^:]+?):(?P<rid>[^:]+?):(?P<lmhash>[^:]+?):(?P<nthash>[^:]+?):')
    for linenum, line in enumerate(file, start=1):
        line = line.rstrip()
        match = pattern.search(line)
        if not match:
            print(f'{file.name}:{linenum}: invalid line: {line}', file=sys.stderr)
            continue
        new_entry = match.groupdict()
        old_entry = result.get(new_entry['longname'])
        # this logic is necessary because in some weird scenarios the samaccountname is not unique
        # see https://github.com/dadevel/bloodhoundcli/issues/9
        if old_entry:
            if new_entry['nthash'] == DISABLED_NTHASH and old_entry['nthash'] != DISABLED_NTHASH:
                pass
            elif new_entry['nthash'] != DISABLED_NTHASH and old_entry['nthash'] == DISABLED_NTHASH:
                result[new_entry['longname']] = new_entry
            elif new_entry['nthash'] != DISABLED_NTHASH and old_entry['nthash'] != DISABLED_NTHASH:
                raise ValueError(f'duplicated user with different nthash, {old_entry=} {new_entry=}')
            elif new_entry['nthash'] == DISABLED_NTHASH and old_entry['nthash'] == DISABLED_NTHASH:
                if new_entry != old_entry:
                    raise ValueError(f'duplicated user both with disabled nthash, {old_entry=} {new_entry=}')
                else:
                    pass
        else:
            result[new_entry['longname']] = new_entry
    return result


def parse_potfile(file: TextIO) -> dict[str, str]:
    """Returns mapping from nthash to password."""
    # format: b9f917853e3dbf6e6831ecce60725930:passw0rd
    pattern = re.compile(r'^([a-f0-9]{32}):(.*?)$')
    result = dict()
    for line in file:
        line = line.rstrip()
        match = pattern.search(line)
        if not match:
            continue
        nthash, password = match.groups()
        result[nthash] = decode_password(password)
    return result
