from datetime import datetime, timedelta, timezone
from typing import Any
import json
import os
import subprocess
import sys

from requests.auth import HTTPBasicAuth
import click
import requests

ENDPOINT = os.environ.get('NEO4J_ENDPOINT') or 'http://localhost:7474'
USERNAME = os.environ.get('NEO4J_USERNAME') or 'neo4j'
PASSWORD = os.environ.get('NEO4J_PASSWORD') or 'neo4j'


@click.group()
def db() -> None:
    pass


@db.command()
@click.argument('name')
def start(name: str) -> None:
    process = subprocess.run(
        [
            'podman', 'run',
            '--name', f'bloodhound-{name}',
            '--detach',
            '--rm',
            '--publish', '127.0.0.1:7474:7474',
            '--publish', '127.0.0.1:7687:7687',
            '--env', 'NEO4J_AUTH=none',
            '--volume', f'bloodhound-{name}:/data',
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


@db.command()
@click.argument('name')
def stop(name: str) -> None:
    subprocess.run(['podman', 'container', 'rm', '-f', f'bloodhound-{name}'], check=True, capture_output=False)


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


def exec_and_print(statement: str, **parameters: Any):
    for row in execute(statement, **parameters):
        if isinstance(row, (bool, int, float, str)):
            print(row)
        else:
            json.dump(row, sys.stdout, indent=None, sort_keys=False)
            sys.stdout.write('\n')


def execute(statement: str, **parameters: Any) -> list[Any]:
    response = requests.post(f'{ENDPOINT}/db/neo4j/tx/commit', json=dict(statements=[dict(statement=statement, parameters=parameters)]), auth=HTTPBasicAuth(USERNAME, PASSWORD))
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
    for line in execute('MATCH (o) WHERE o:User or o:Computer RETURN o.samaccountname AS line UNION MATCH (o:OU) RETURN left(o.name, size(o.name) - size(o.domain) - 1) AS line UNION MATCH (o) WHERE o.description IS NOT NULL RETURN o.description AS line'):
        if not line:
            continue
        print(line.upper())
        print(line.lower())


def find_shared_passwords() -> None:
    count = sum(execute(
        "MATCH (a:User) MATCH (b:User) WHERE a<>b AND NOT a.nthash IS null AND a.nthash=b.nthash MERGE (a)-[:SharesPasswordWith]-(b) RETURN count(b)"
    ))
    print(f'created {count} edges for shared hashes')
