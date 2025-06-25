from __future__ import annotations
from typing import Any, Generator
import importlib.resources
import json
import os
import re
import sys

from requests.auth import HTTPBasicAuth
import click
import requests

from bloodhoundcli import data as resources  # type: ignore

NEO4J_URL = os.environ.get('NEO4J_URL') or 'http://localhost:7474'
NEO4J_USERNAME = os.environ.get('NEO4J_USERNAME') or 'neo4j'
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD') or ''
WORD_SEPARATOR_PATTERN = re.compile(r'[^a-zA-Z0-9]')
EDGE_TYPE_PATTERN = re.compile('^[a-zA-z_]+$')


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
        self.run_post_processing_queries()

    def assign_weights(self) -> None:
        for edge_type in self.execute('MATCH ()-[r]->() RETURN DISTINCT type(r)'):
            assert EDGE_TYPE_PATTERN.fullmatch(edge_type)
            weight = self.EDGE_WEIGHTS.get(edge_type)
            if weight is None:
                print(f'using default weight for {edge_type} edges')
            self.execute(f"MATCH ()-[r:{edge_type}]->() SET r.cost=$weight", weight=self.DEFAULT_WEIGHT if weight is None else weight)

    def create_indices(self) -> None:
        print('indexing user names')
        self.execute('CREATE INDEX ad_user_name_index IF NOT EXISTS FOR (u:User) ON (u.name)')
        print('indexing computer names')
        self.execute('CREATE INDEX ad_computer_name_index IF NOT EXISTS FOR (c:Computer) ON (c.name)')
        print('indexing user domains')
        self.execute('CREATE INDEX ad_user_domain_index IF NOT EXISTS FOR (u:User) ON (u.domain)')
        print('indexing computer domains')
        self.execute('CREATE INDEX ad_computer_domain_index IF NOT EXISTS FOR (c:Computer) ON (c.domain)')
        print('indexing user samaccountnames')
        self.execute('CREATE INDEX ad_user_samaccountname_index IF NOT EXISTS FOR (u:User) ON (u.samaccountname)')
        print('indexing computer samaccountnames')
        self.execute('CREATE INDEX ad_computer_samaccountname_index IF NOT EXISTS FOR (c:Computer) ON (c.samaccountname)')
        print('indexing credential object ids')
        self.execute('CREATE INDEX ad_credential_objectid_index IF NOT EXISTS FOR (c:Credential) ON (c.objectid)')

    def run_post_processing_queries(self) -> None:
        print('running post-processing queries')

        # load queries from customqueries.json
        with importlib.resources.path(resources, 'customqueries.json') as path:
            with open(path, 'r') as file:
                data = json.load(file)

        # execute all enrichment queries
        for item in data['queries']:
            if item.get('enrich'):
                for item in item['queryList']:
                    self.execute(item['query'])


@click.command(help='Execute Cypher statement')
@click.argument('statement')
@click.option('-s', '--stdin', is_flag=True)
@click.option('-j', '--jsonl', is_flag=True)
def query(statement: str, stdin: bool, jsonl: bool) -> None:
    if stdin and not statement:
        raise RuntimeError('invalid arugment combination')

    if not statement or statement == '-':
        statement = sys.stdin.read()

    db = Database.from_env()
    try:
        if stdin:
            for line in sys.stdin:
                if jsonl:
                    line = json.loads(line)
                else:
                    line = line.rstrip()
                for row in db.execute(statement, stdin=line):
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


@click.command(help='Enrich Neo4j data')
def enrich() -> None:
    db = Database.from_env()
    db.enrich()


def generate_words(value: str, reverse: bool = False) -> Generator[str, None, None]:
    value = value.replace('\n', ' ')
    value = value.replace('\r', ' ')
    value = value.replace('\t', ' ')

    if reverse:
        yield value[::-1]
        yield value.upper()[::-1]
        yield value.lower()[::-1]
    else:
        yield value
        yield value.lower()
        yield value.upper()

    # split value into multiple parts, e.g. 'One/Two-Three' would become ['One', 'Two', 'Three']
    for part in WORD_SEPARATOR_PATTERN.split(value):
        if not part:
            continue
        if reverse:
            yield part[::-1]
            yield part.upper()[::-1]
            yield part.lower()[::-1]
        else:
            yield part
            yield part.lower()
            yield part.upper()


@click.command(help='Print wordlist based on object names and descriptions')
def generate_wordlist() -> None:
    db = Database.from_env()

    # add passwords
    for line in db.execute('MATCH (c:Credential) WHERE c.password IS NOT NULL RETURN c.password'):
        print(line)

    words = set()

    # add names and descriptions of users, computers, groups and OUs
    for line in db.execute('MATCH (o) WHERE (o:User OR o:Computer OR o:Group) AND o.samaccountname IS NOT NULL RETURN o.samaccountname AS line UNION MATCH (o) WHERE (o:OU OR o:Domain) AND o.name IS NOT NULL AND o.domain IS NOT NULL AND size(o.name) > size(o.domain) RETURN DISTINCT left(o.name, size(o.name) - size(o.domain) - 1) AS line UNION MATCH (o) WHERE o.description IS NOT NULL RETURN o.description AS line'):
        if not line:
            continue
        if isinstance(line, list):
            line = ' '.join(line)
        if line.endswith('$'):
            line = line.rstrip('$')
        words.update(generate_words(line))
        for part in line.split(' '):
            words.update(generate_words(part))

    # add reverse username, 'alice' would become 'ecila'
    for line in db.execute('MATCH (u:User) WHERE u.samaccountname IS NOT NULL RETURN u.samaccountname'):
        if not line:
            continue
        words.update(generate_words(line, reverse=True))
        for part in line.split(' '):
            words.update(generate_words(part, reverse=True))

    for word in words:
        print(word)
