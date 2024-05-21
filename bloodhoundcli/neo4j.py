from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Generator
import json
import os
import shlex
import subprocess
import sys
import time
import re

from requests.auth import HTTPBasicAuth
import click
import requests

NEO4J_CONTAINER_PREFIX = 'bloodhound'
NEO4J_URL = os.environ.get('NEO4J_URL') or 'http://localhost:7474'
NEO4J_USERNAME = os.environ.get('NEO4J_USERNAME') or 'neo4j'
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD') or ''


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
        return cls(NEO4J_URL, NEO4J_USERNAME, NEO4J_PASSWORD)

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
    @classmethod
    def get_status(cls, name: str) -> str:
        # valid status values: created, exited, paused, running, unknown
        container_name = f'{NEO4J_CONTAINER_PREFIX}-{name}'
        process = subprocess.run(['podman', 'container', 'inspect', container_name], check=False, capture_output=True, text=True)
        if process.returncode != 0:
            return 'inexistent'
        entries = json.loads(process.stdout)
        assert len(entries) == 1
        return entries[0]['State']['Status']

    @classmethod
    def get_instances(cls) -> Generator[tuple[str, str], None, None]:
        prefix = f'{NEO4J_CONTAINER_PREFIX}-'
        process = subprocess.run(['podman', 'ps', '--all', '--format', 'json'], check=True, capture_output=True, text=True)
        for container in json.loads(process.stdout):
            for container_name in container['Names']:
                if container_name.startswith(prefix):
                    yield container_name.removeprefix(prefix), container['State']

    @classmethod
    def get_env_config(cls) -> dict[str, str]:
        return dict(NEO4J_URL=NEO4J_URL, NEO4J_USERNAME=NEO4J_USERNAME, NEO4J_PASSWORD=NEO4J_PASSWORD)

    @classmethod
    def setup(cls, name: str) -> dict[str, str]:
        for instance, status in cls.get_instances():
            if instance != name and status == 'running':
                cls.stop(instance)
        status = cls.get_status(name)
        if status == 'inexistent':
            cls.create(name)
        if status != 'running':
            cls.start(name)
        return cls.get_env_config()

    @classmethod
    def create(cls, name: str) -> None:
        print(f'creating {name}')
        container_name = f'{NEO4J_CONTAINER_PREFIX}-{name}'
        # NEO4J_PLUGINS/NEO4JLABS_PLUGINS threw errors, instead the gds plugin was directly built into the image
        process = subprocess.run(
            [
                'podman', 'create',
                '--name', container_name,
                #'--rm',
                '--publish', f'127.0.0.1:7474:7474',
                '--publish', f'127.0.0.1:7687:7687',
                '--env', f'NEO4J_AUTH={NEO4J_USERNAME}/{NEO4J_PASSWORD}' if NEO4J_USERNAME and NEO4J_PASSWORD else 'NEO4J_AUTH=none',
                #'--volume', f'{name}:/data',
                'ghcr.io/dadevel/neo4j:4.4.12',
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        container_id = process.stdout.strip()
        timestamp = (datetime.now(tz=timezone.utc) + timedelta(seconds=15)).isoformat()
        subprocess.run(['podman', 'container', 'logs', '--follow', '--until', timestamp, container_id], check=True, capture_output=False)

    @classmethod
    def remove(cls, name: str) -> None:
        print(f'removing {name}')
        container_name = f'{NEO4J_CONTAINER_PREFIX}-{name}'
        subprocess.run(['podman', 'container', 'rm', '-f', container_name], check=True, capture_output=False)

    @classmethod
    def start(cls, name: str) -> None:
        print(f'starting {name}')
        container_name = f'{NEO4J_CONTAINER_PREFIX}-{name}'
        subprocess.run(['podman', 'container', 'start', container_name], check=True, capture_output=False)

    @classmethod
    def stop(cls, name: str) -> None:
        print(f'stopping {name}')
        container_name = f'{NEO4J_CONTAINER_PREFIX}-{name}'
        subprocess.run(['podman', 'container', 'stop', container_name], check=True, capture_output=False)



@click.command('list', help='List Neo4j containers')
def neo4j_list() -> None:
    for name, state in DatabaseManager.get_instances():
        click.echo(f'{name} {state}')


@click.command('setup', help='Stop other containers, then run the given container')
@click.argument('name')
def neo4j_setup(name: str) -> None:
    env_vars = DatabaseManager.setup(name)
    click.echo('\n'.join(f'{key}={shlex.quote(value)}' for key, value in env_vars.items()))


@click.command('delete', help='Remove Neo4j container')
@click.argument('name')
def neo4j_delete(name: str) -> None:
    DatabaseManager.remove(name)


def query(statement: str, stdin: bool) -> None:
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


def print_row(row: Any) -> None:
    if isinstance(row, (bool, int, float, str)):
        print(row)
    else:
        json.dump(row, sys.stdout, indent=None, sort_keys=False)
        sys.stdout.write('\n')


@click.command(help='Import SharpHound/BloodHound.py ZIP')
@click.argument('path')
def import_sharphound(path: str) -> None:
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


@click.command('enrich', help='Add indices and weights')
def neo4j_enrich() -> None:
    """Add shared passwords and edge costs."""
    db = Database.from_env()
    db.enrich()


def process_word_for_wordlist(word: str, words: Set[str], add_reverse: bool = False) -> None:
    # First, add the original string to the wordlist.
    words.add(word)

    # Split the string into multiple words, if it contains any characters that resemble separators.
    # For example "One/Two-Three" would become "One", "Two", "Three".
    separator_pattern = r'[-_.,:;+&%#$/\s\\]'
    parts = re.split(separator_pattern, word)

    # Treat each part of the splitted string as a word and generate common variants.
    for part in parts:
        add_word_variants_to_wordlist(part, words, add_reverse)


def add_word_variants_to_wordlist(word: str, words: Set[str], add_reverse: bool = False) -> None:
    # Add lowercase and uppercase representations of the word.
    words.add(word.lower())
    words.add(word.upper())

    # If requested, add a reversed representation of the lowercase word to the wordlist.
    if add_reverse:
        words.add(word.lower()[::-1])


@click.command(help='Print wordlist based on object names and descriptions')
def generate_wordlist() -> None:
    db = Database.from_env()
    words = set()

    for line in db.execute('MATCH (o) WHERE (o:User OR o:Computer OR o:Group) AND o.samaccountname IS NOT NULL RETURN o.samaccountname AS line UNION MATCH (o) WHERE (o:OU OR o:Domain) AND o.name IS NOT NULL AND o.domain IS NOT NULL AND size(o.name) > size(o.domain) RETURN DISTINCT left(o.name, size(o.name) - size(o.domain) - 1) AS line UNION MATCH (o) WHERE o.description IS NOT NULL RETURN o.description AS line'):
        if not line:
            continue
        if line.endswith('$'):
            line = line.rstrip('$')
        for word in line.split():
            # Run the words through some conversions (like splitting, `upper()`, and `lower()`) and add them to the wordlist.
            process_word_for_wordlist(word, words)

    for line in db.execute('MATCH (o) WHERE (o:User) AND o.samaccountname IS NOT NULL RETURN o.samaccountname AS line'):
        if not line:
            continue
        for word in line.split():
            # Only for usernames: Also add a reversed representation (for example, "alice" would become "ecila").
            process_word_for_wordlist(word, words, add_reverse=True)

    for word in words:
        print(word)
