from pathlib import Path
import importlib.resources
import json
import os
import time

from requests import Session
import requests
import click

from bloodhoundcli import data as resources  # type: ignore

BLOODHOUND_URL = os.environ.get('BLOODHOUND_URL') or 'http://localhost:7575'
BLOODHOUND_USERNAME = os.environ.get('BLOODHOUND_USERNAME') or 'admin'
BLOODHOUND_PASSWORD = os.environ.get('BLOODHOUND_PASSWORD') or ''


def wait_until_up() -> None:
    print('waiting for BHCE')
    while True:
        try:
            response = requests.get(f'{BLOODHOUND_URL}/ui/')
            response.raise_for_status()
            return
        except requests.exceptions.ConnectionError:
            time.sleep(1)


def login() -> Session:
    session = Session()
    response = session.post(f'{BLOODHOUND_URL}/api/v2/login', json=dict(login_method='secret', username=BLOODHOUND_USERNAME, secret=BLOODHOUND_PASSWORD))
    response.raise_for_status()
    data = response.json()
    session.headers.update({'Authorization': f'Bearer {data['data']['session_token']}'})
    return session


def import_custom_queries(session: Session) -> None:
    with importlib.resources.open_text(resources, 'customqueries.json') as file:
        queries = json.load(file)

    expected_queries = {}
    for item in queries['queries']:
        if item['category']:
            name = f'{item['category']}: {item['name']}'
        else:
            name = item['name']
        if len(item['queryList']) > 1:
            print(f'warning: can not import query {name!r} because it has more than one subquery which is not supported by BHCE')
            continue
        if name in expected_queries:
            print(f'warning: duplicated query {name!r}')
            continue
        expected_queries[name] = item['queryList'][0]['query']

    response = session.get(f'{BLOODHOUND_URL}/api/v2/saved-queries')
    response.raise_for_status()
    queries = response.json()
    actual_queries = {item['name']: item['query'] for item in queries['data']}

    for name in expected_queries|actual_queries:
        if name in expected_queries and name not in actual_queries:
            create_query(session, name, expected_queries[name])
        if name in expected_queries and name in actual_queries:
            if expected_queries[name] != actual_queries[name]:
                delete_query(session, name)
                create_query(session, name, expected_queries[name])


def create_query(session: Session, name: str, statement: str) -> None:
    tries = 0
    while True:
        response = session.post(f'{BLOODHOUND_URL}/api/v2/saved-queries', json=dict(name=name, query=statement))
        if response.ok:
            return
        if response.status_code == 429:
            if tries > 3:
                response.raise_for_status()
            tries += 1
            time.sleep(1)


def delete_query(session: Session, name: str) -> None:
    tries = 0
    while True:
        response = session.delete(f'{BLOODHOUND_URL}/api/v2/saved-queries', json=dict(name=name))
        if response.ok:
            return
        if response.status_code == 429:
            if tries > 3:
                response.raise_for_status()
            tries += 1
            time.sleep(1)


def ingest_file(session: Session, path: Path) -> None:
    response = session.post(f'{BLOODHOUND_URL}/api/v2/file-upload/start')
    response.raise_for_status()
    data = response.json()
    job_id = data['data']['id']
    with open(path, mode='rb') as file:
        data = file.read()
    response = session.post(f'{BLOODHOUND_URL}/api/v2/file-upload/{job_id}', data=data, headers={'Content-Type': f'application/{path.suffix.removeprefix('.')}'})
    response.raise_for_status()
    response = session.post(f'{BLOODHOUND_URL}/api/v2/file-upload/{job_id}/end')
    response.raise_for_status()


def ingest_files(session: Session, paths: list[Path]) -> None:
    for path in paths:
        if path.suffix not in ('.json', '.zip'):
            print(f'error: {path}: unsupported file extension')
            continue
        ingest_file(session, path)
    print('upload complete, ingestion can take some time')


@click.command()
@click.argument('file', type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path), nargs=-1)
def import_bhce(file: list[Path]) -> None:
    if not file:
        return
    session = login()
    ingest_files(session, file)
