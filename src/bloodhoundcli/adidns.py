from typing import TypedDict, TextIO
import csv

import click

from bloodhoundcli.neo4j import Database


@click.command(help='Import computers from ADIDNS CSV')
@click.argument('domain',)
@click.argument('file', type=click.File('r'))
def import_adidns(domain: str, file: TextIO) -> None:
    neo4j = Database.from_env()
    neo4j.create_indices()

    # generate list of DNSEntry objects (only A records are used)
    output = [
        DNSEntry(record_type=row[0], zone=domain, hostname=row[1], ip=row[2])
        for row in csv.reader(file)
        if row[0] == 'A'
    ]

    # count updated and created nodes
    new_nodes = 0
    existing_nodes = 0
    for entry in output:
        fqdn = f'{entry['hostname']}.{entry['zone']}'.upper()
        # check if node with hostname already exists
        exists = sum(neo4j.execute('MATCH (c:Computer {name: $name}) RETURN 1', name=fqdn))
        if exists:
            # update attribute if computer already exists
            neo4j.execute('MATCH (c:Computer {name: $name}) SET c.ipaddress=$ip RETURN 1', name=fqdn, ip=entry['ip'])
            existing_nodes += 1
        else:
            # otherwise create new computer
            neo4j.execute('CREATE (c:Base:Computer {objectid: $name, name: $name, samaccountname: $hostname + "$", standalone: true, ipaddress: $ip})', name=fqdn, hostname=entry['hostname'], ip=entry['ip'])
            new_nodes += 1

    print(f'{existing_nodes} computer objects updated')
    print(f'{new_nodes} computer objects created')


class DNSEntry(TypedDict):
    record_type: str
    zone: str
    hostname: str
    ip: str
