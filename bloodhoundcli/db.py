from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Generator
import json
import os
import subprocess
import sys
import time

from requests.auth import HTTPBasicAuth
import click
import requests


class Database:
    DEFAULT_WEIGHT = 50
    EDGE_WEIGHTS = dict(
        GetChangesInFilteredSet=100,
        GetChangesAll=100,
        GetChanges=100,
        ForceChangePassword=90,
        GPLink=80,
        ExecuteDCOM=70,
        CanPSRemote=60,
        CanRDP=60,
        HasSession=50,
        HasSIDHistory=40,
        WriteAccountRestrictions=40,
        WriteDacl=30,
        WriteOwner=30,
        AddKeyCredentialLink=30,
        GenericWrite=30,
        AllExtendedRights=20,
        GenericAll=20,
        Owns=20,
        AdminTo=10,
        SyncLAPSPassword=10,
        DCSync=10,
        AddMember=5,
        ReadLAPSPassword=5,
        Contains=1,
        MemberOf=1,
    )

    def __init__(self, url: str, username: str, password: str) -> None:
        self.url = url
        self.username = username
        self.password = password

    @classmethod
    def from_env(cls) -> Database:
        return cls(
            os.environ.get('NEO4J_URL') or 'http://localhost:7474',
            os.environ.get('NEO4J_USERNAME') or 'neo4j',
            os.environ.get('NEO4J_PASSWORD') or 'neo4j',
        )

    def execute(self, statement: str, **parameters: Any) -> list[Any]:
        response = requests.post(
            f'{self.url}/db/neo4j/tx/commit',
            json=dict(statements=[dict(statement=statement, parameters=parameters)]),
            auth=HTTPBasicAuth(self.username, self.password),
        )
        body = response.json()
        if body['errors']:
            raise RuntimeError('\n'.join(error['message'] for error in body['errors']))
        return [
            row
            for result in body['results']
            for data in result['data']
            for row in data['row']
        ]

    def enrich(self) -> None:
        self.create_indices()
        self.assign_weights()
        # TODO: add reverse edge for HasSession

    def assign_weights(self) -> None:
        for edge_type in self.execute('MATCH ()-[r]->() RETURN DISTINCT type(r)'):
            assert edge_type.isalnum()
            weight = self.EDGE_WEIGHTS.get(edge_type)
            if weight is None:
                print(f'using default weight for {edge_type} edges')
            self.execute(f"MATCH ()-[r:{edge_type}]->() SET r.cost=$weight", weight=self.DEFAULT_WEIGHT if weight is None else weight)

    def create_indices(self) -> None:
        self.execute('CREATE INDEX ad_user_name_index IF NOT EXISTS FOR (u:User) ON (u.name)')
        self.execute('CREATE INDEX ad_computer_name_index IF NOT EXISTS FOR (c:Computer) ON (c.name)')
        self.execute('CREATE INDEX ad_user_domain_index IF NOT EXISTS FOR (u:User) ON (u.domain)')
        self.execute('CREATE INDEX ad_computer_domain_index IF NOT EXISTS FOR (c:Computer) ON (c.domain)')
        self.execute('CREATE INDEX ad_user_samaccountname_index IF NOT EXISTS FOR (u:User) ON (u.samaccountname)')
        self.execute('CREATE INDEX ad_computer_samaccountname_index IF NOT EXISTS FOR (c:Computer) ON (c.samaccountname)')
        self.execute('CREATE INDEX ad_credential_objectid_index IF NOT EXISTS FOR (c:Credential) ON (c.objectid)')


class DatabaseManager:
    NEO4J_CONTAINER_PREFIX = 'bloodhound'

    @classmethod
    def create(cls, name: str, bolthost: str = '127.0.0.1:7474', webhost: str = '127.0.0.1:7687', username: str = 'neo4j', password: str = '') -> dict[str, str]:
        container_name = f'{cls.NEO4J_CONTAINER_PREFIX}-{name}'
        # NEO4J_PLUGINS/NEO4JLABS_PLUGINS threw errors, instead the gds plugin was directly built into the image
        process = subprocess.run(
            [
                'podman', 'run',
                '--name', container_name,
                '--detach',
                #'--rm',
                '--publish', f'{bolthost}:7474',
                '--publish', f'{webhost}:7687',
                '--env', f'NEO4J_AUTH={username}/{password}' if username and password else 'NEO4J_AUTH=none',
                #'--volume', f'{name}:/data',
                'ghcr.io/dadevel/neo4j:4.4.12',
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        container_id = process.stdout.strip()
        timestamp = (datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(seconds=15)).isoformat()
        subprocess.run(['podman', 'container', 'logs', '--follow', '--until', timestamp, container_id], check=True, capture_output=False)
        return dict(NEO4J_URL=f'http://{bolthost}', NEO4J_USERNAME=username, NEO4J_PASSWORD=password)

    @classmethod
    def destroy(cls, name: str) -> None:
        container_name = f'{cls.NEO4J_CONTAINER_PREFIX}-{name}'
        subprocess.run(['podman', 'container', 'rm', '-f', container_name], check=True, capture_output=True, text=True)

    @classmethod
    def start(cls, name: str) -> None:
        container_name = f'{cls.NEO4J_CONTAINER_PREFIX}-{name}'
        subprocess.run(['podman', 'container', 'start', container_name], check=True, capture_output=True, text=True)

    @classmethod
    def stop(cls, name: str) -> None:
        container_name = f'{cls.NEO4J_CONTAINER_PREFIX}-{name}'
        subprocess.run(['podman', 'container', 'stop', container_name], check=True, capture_output=True, text=True)

    @classmethod
    def instances(cls) -> Generator[tuple[str, str], None, None]:
        prefix = f'{cls.NEO4J_CONTAINER_PREFIX}-'
        process = subprocess.run(['podman', 'ps', '--all', '--format', 'json'], check=True, capture_output=True, text=True)
        for container in json.loads(process.stdout):
            for container_name in container['Names']:
                if container_name.startswith(prefix):
                    yield container_name.removeprefix(prefix), container['State']


@click.group()
def db() -> None:
    pass


@db.command(name='list')
def list_() -> None:
    for name, state in DatabaseManager.instances():
        click.echo(f'{name} {state}')


@db.command()
@click.argument('name')
def create(name: str) -> None:
    opts = DatabaseManager.create(name)
    click.echo('\n'.join(f'{key}={value}' for key, value in opts.items()))


@db.command()
@click.argument('name')
def destroy(name: str) -> None:
    DatabaseManager.destroy(name)


@db.command()
@click.argument('name')
def start(name: str) -> None:
    DatabaseManager.start(name)


@db.command()
@click.argument('name')
def stop(name: str) -> None:
    DatabaseManager.stop(name)


def print_row(row: Any) -> None:
    if isinstance(row, (bool, int, float, str)):
        print(row)
    else:
        json.dump(row, sys.stdout, indent=None, sort_keys=False)
        sys.stdout.write('\n')


@db.command()
@click.argument('statement')
@click.option('-s', '--stdin', is_flag=True)
def query(stdin: bool, statement: str) -> None:
    if stdin and not statement:
        raise RuntimeError('invalid arugment combination')

    if not statement or statement == '-':
        statement = sys.stdin.read()

    db = Database.from_env()
    try:
        if stdin:
            for line in sys.stdin:
                for row in db.execute(statement, stdin=line.rstrip()):
                    print_row(row)
        else:
            for row in db.execute(statement):
                print_row(row)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        exit(1)


@db.command()
@click.argument('path')
def ingest(path: str) -> None:
    # TODO: start postgres and bloodhoundce-api containers
    # podman run --name bloodhound-postgres -it --rm --network host -e POSTGRES_USER=bloodhound -e POSTGRES_PASSWORD=bloodhound -e POSTGRES_DATABASE=bloodhound docker.io/library/postgres:13.2
    # podman run --name bloodhound-api -it --rm --network host -v ./bloodhound.config.json:/bloodhound.config.json docker.io/specterops/bloodhound:latest
    endpoint = os.environ.get('BLOODHOUND_URL') or 'http://localhost:8080'
    username = os.environ.get('BLOODHOUND_USERNAME') or click.prompt('username')
    password = os.environ.get('BLOODHOUND_PASSWORD') or click.prompt('password', hide_input=True)
    with requests.Session() as session:
        click.echo('authenticating')
        response = session.post(f'{endpoint}/api/v2/login', headers=dict(accept='application/json'), json=dict(login_method='secret', username=username, secret=password))
        response.raise_for_status()
        response = response.json()
        token = response['data']['session_token']

        click.echo('starting upload')
        response = session.post(f'{endpoint}/api/v2/file-upload/start', headers=dict(accept='application/json', authorization=f'Bearer {token}'))
        response.raise_for_status()
        response = response.json()
        upload_id = response['data']['id']
        click.echo(f'id: {upload_id}')

        click.echo('uploading')
        with open(path, 'rb') as file:
            response = session.post(f'{endpoint}/api/v2/file-upload/{upload_id}', headers=dict(accept='application/json', authorization=f'Bearer {token}'), data=file.read())
            response.raise_for_status()

        click.echo('ending upload')
        response = session.post(f'{endpoint}/api/v2/file-upload/{upload_id}/end', headers=dict(accept='application/json', authorization=f'Bearer {token}'))
        response.raise_for_status()

        click.echo('awaiting ingestion')
        completed = False
        while not completed:
            response = session.get(f'{endpoint}/api/v2/file-upload', headers=dict(accept='application/json', authorization=f'Bearer {token}'))
            response.raise_for_status()
            response = response.json()
            for item in response['data']:
                if item['id'] == upload_id and item['status'] == 2:
                    completed = True
                    break
            time.sleep(1)


@db.command()
def enrich() -> None:
    """Add shared passwords and edge costs."""
    db = Database.from_env()
    db.enrich()


@db.command()
def generate_wordlist() -> None:
    db = Database.from_env()
    words = set()
    for line in db.execute('MATCH (o) WHERE (o:User OR o:Computer OR o:Group) AND o.samaccountname IS NOT NULL RETURN o.samaccountname AS line UNION MATCH (o) WHERE (o:OU OR o:Domain) AND o.name IS NOT NULL AND o.domain IS NOT NULL AND size(o.name) > size(o.domain) RETURN DISTINCT left(o.name, size(o.name) - size(o.domain) - 1) AS line UNION MATCH (o) WHERE o.description IS NOT NULL RETURN o.description AS line'):
        if not line:
            continue
        if line.endswith('$'):
            line = line.rstrip('$')
        for word in line.split():
            words.add(word)
            if word.isupper():
                words.add(word.lower())
            else:
                words.add(word)
    for word in words:
        print(word)
