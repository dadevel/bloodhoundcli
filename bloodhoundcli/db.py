from datetime import datetime, timedelta, timezone
from typing import Any
import json
import os
import subprocess
import sys
import time

from requests.auth import HTTPBasicAuth
import click
import requests

NEO4J_URL = os.environ.get('NEO4J_URL') or 'http://localhost:7474'
NEO4J_USERNAME = os.environ.get('NEO4J_USERNAME') or 'neo4j'
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD') or 'neo4j'
NEO4J_CONTAINER_PREFIX = 'bloodhound'


@click.group()
def db() -> None:
    pass


@db.command()
@click.argument('name')
def start(name: str) -> None:
    start_neo4j(f'{NEO4J_CONTAINER_PREFIX}-{name}')


@db.command()
@click.argument('name')
def stop(name: str) -> None:
    stop_neo4j(f'{NEO4J_CONTAINER_PREFIX}-{name}')


@db.command()
@click.argument('name')
def delete(name: str) -> None:
    stop_neo4j(f'{NEO4J_CONTAINER_PREFIX}-{name}', check=False)
    delete_neo4j_volume(f'{NEO4J_CONTAINER_PREFIX}-{name}')


@db.command()
@click.argument('name')
def switch(name: str) -> None:
    process = subprocess.run(['podman', 'ps', '--format', 'json'], check=True, capture_output=True, text=True)
    for container in json.loads(process.stdout):
        for container_name in container['Names']:
            if container_name.startswith(f'{NEO4J_CONTAINER_PREFIX}-'):
                click.echo(f'stopping {container_name}')
                stop_neo4j(container_name)
    start_neo4j(f'{NEO4J_CONTAINER_PREFIX}-{name}')


@db.command()
@click.argument('statement')
@click.option('-s', '--stdin', is_flag=True)
def query(stdin: bool, statement: str) -> None:
    if stdin and not statement:
        raise RuntimeError('invalid arugment combination')

    if not statement or statement == '-':
        statement = sys.stdin.read()

    try:
        if stdin:
            for line in sys.stdin:
                exec_and_print(statement, stdin=line.rstrip())
        else:
            exec_and_print(statement)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        exit(1)


@db.command()
@click.argument('path')
def ingest(path: str) -> None:
    # TODO: start postgres and bloodhoundce-api containers
    # podman run --name bloodhound-postgres -it --rm --network host -e POSTGRES_USER=bloodhound -e POSTGRES_PASSWORD=bloodhound -e POSTGRES_DATABASE=bloodhound docker.io/library/postgres:13.2
    # podman run --name bloodhound-api -it --rm --network host -v ./bloodhound.config.json:/bloodhound.config.json docker.io/specterops/bloodhound:latest
    # ./bloodhound.config.json sample is stored in repo root
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


def start_neo4j(name: str) -> None:
    process = subprocess.run(
        [
            'podman', 'run',
            '--name', name,
            '--detach',
            '--rm',
            '--publish', '127.0.0.1:7474:7474',
            '--publish', '127.0.0.1:7687:7687',
            '--env', 'NEO4J_AUTH=none',
            '--volume', f'{name}:/data',
            'docker.io/library/neo4j:4.4.12',
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    container_id = process.stdout.strip()
    print(container_id)
    timestamp = (datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(seconds=15)).isoformat()
    subprocess.run(['podman', 'container', 'logs', '--follow', '--until', timestamp, container_id], check=True, capture_output=False)


def stop_neo4j(name: str, check: bool = False) -> None:
    subprocess.run(['podman', 'container', 'stop', name], check=check, capture_output=True)


def delete_neo4j_volume(name: str) -> None:
    subprocess.run(['podman', 'volume', 'rm', name], check=False, capture_output=True)


def exec_and_print(statement: str, **parameters: Any):
    for row in execute(statement, **parameters):
        if isinstance(row, (bool, int, float, str)):
            print(row)
        else:
            json.dump(row, sys.stdout, indent=None, sort_keys=False)
            sys.stdout.write('\n')


def execute(statement: str, **parameters: Any) -> list[Any]:
    response = requests.post(f'{NEO4J_URL}/db/neo4j/tx/commit', json=dict(statements=[dict(statement=statement, parameters=parameters)]), auth=HTTPBasicAuth(NEO4J_USERNAME, NEO4J_PASSWORD))
    body = response.json()
    if body['errors']:
        raise RuntimeError('\n'.join(error['message'] for error in body['errors']))
    return [
        row
        for result in body['results']
        for data in result['data']
        for row in data['row']
    ]


@db.command()
def generate_wordlist() -> None:
    words = set()
    for line in execute('MATCH (o) WHERE (o:User OR o:Computer OR o:Group) AND o.samaccountname IS NOT NULL RETURN o.samaccountname AS line UNION MATCH (o) WHERE (o:OU OR o:Domain) AND o.name IS NOT NULL AND o.domain IS NOT NULL AND size(o.name) > size(o.domain) RETURN DISTINCT left(o.name, size(o.name) - size(o.domain) - 1) AS line UNION MATCH (o) WHERE o.description IS NOT NULL RETURN o.description AS line'):
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


def find_shared_passwords() -> None:
    count = sum(execute(
        "MATCH (a:User) MATCH (b:User) WHERE a<>b AND NOT a.nthash IS null AND a.nthash=b.nthash MERGE (a)-[:SharesPasswordWith]-(b) RETURN count(b)"
    ))
    print(f'created {count} edges for shared hashes')
