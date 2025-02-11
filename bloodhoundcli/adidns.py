from pathlib import Path
from typing import TextIO, TypedDict

import click

from bloodhoundcli.neo4j import Database


@click.command(help='Import Adidns output to create and update existing nodes')
@click.argument('adidns', type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path), nargs=-1)


def import_adidns(adidns: list[Path]) -> None:
    neo4j = Database.from_env()
    neo4j.create_indices()

    output = []

    # Generate list of DNSEntry objects (only A records are used)
    for path in adidns:
        try:
            with open(path, 'r') as file:
                lines = [line.rstrip() for line in file]
                records = [x.split(',') for x in lines]
                for entry in records:
                    if entry[0] == 'A':
                        output.append(DNSEntry(record_type=entry[0], hostname=entry[1], ip=entry[2]))

        except Exception as e:
            adinds = {}
            print(f'error: failed to load file: {e}')


    # Used to count updated and created nodes
    new_nodes = 0
    existing_nodes = 0
    # Update database
    for entry in output:
        # Check if node with hostname already exists
        count=sum(neo4j.execute("MATCH (c:Computer) where substring(toLower(c.samaccountname), 0, size(c.samaccountname) - 1)=toLower($hostname) return 1", hostname=entry['hostname']))


        if count == 1:
            # If host already exists then the attribute IP is updated
            neo4j.execute("MATCH (c:Computer) where substring(toLower(c.samaccountname), 0, size(c.samaccountname) - 1)=toLower($hostname) SET c.ip=$ip return 1", hostname=entry['hostname'], ip=entry['ip'])
            existing_nodes += 1
        else:
            # If no host with corresponding samaccountname exists a new node is created
            neo4j.execute("CREATE (c:Computer {samaccountname: $hostname, ip: $ip})", hostname=str(entry['hostname']) + '$', ip=entry['ip'])
            new_nodes += 1


    print(f'{existing_nodes} computer objects updated')
    print(f'{new_nodes} computer objects created')



class DNSEntry(TypedDict):
    record_type: str
    hostname: str
    ip: str


