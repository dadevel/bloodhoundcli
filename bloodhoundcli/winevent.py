import json
import sys

import click

from bloodhoundcli import db

LOGON_TYPE_TABLE = {
    0: 'system',
    2: 'interactive',
    3: 'network',
    4: 'batch',
    5: 'service',
    6: 'proxy',
    7: 'unlock',
    8: 'network-cleartext',
    9: 'new-credentials',
    10: 'remote-interactive',
    11: 'cached-interactive',
    12: 'cached-remote-interactive',
    13: 'cached-unlock',

}


@click.group()
def winevent() -> None:
    pass


@winevent.command('import')
@click.argument('eventfile', default='-')
def import_(eventfile: str) -> None:
    file = sys.stdin if eventfile == '-' else open(eventfile)
    with file:
        events = json.load(file)
    for event in events:
        authpkg = event.get('authenticationpackage')
        if authpkg:
            authpkg = authpkg.lower()
        db.execute(
            'MATCH (c:Computer {name: $computerfqdn}) MATCH (u:User {objectid: $usersid}) MERGE (c)-[r:HadSession]->(u) SET r.timestamp=$timestamp, r.logontype=$logontype, r.authenticationpackage=$authenticationpackage',
            computerfqdn=event['computerfqdn'].upper(),
            usersid=event['usersid'],
            timestamp=event.get('timestamp'),
            logontype=LOGON_TYPE_TABLE.get(event.get('logontype')),
            authenticationpackage=authpkg,
        )
        if event.get('elevated'):
            db.execute(
                'MATCH (c:Computer {name: $computerfqdn}) MATCH (u:User {objectid: $usersid}) MERGE (u)-[:AdminTo]->(c)',
                computerfqdn=event['computerfqdn'].upper(),
                usersid=event['usersid'],
            )
        elif event.get('logontype') == 10:
            db.execute(
                'MATCH (c:Computer {name: $computerfqdn}) MATCH (u:User {objectid: $usersid}) MERGE (u)-[:CanRDP]->(c)',
                computerfqdn=event['computerfqdn'].upper(),
                usersid=event['usersid'],
            )
