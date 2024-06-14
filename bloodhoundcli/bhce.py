import importlib.resources
import json
import os
import time

from requests import Session
import requests

from bloodhoundcli import data  # type: ignore

BLOODHOUND_URL = os.environ.get('BLOODHOUND_URL') or 'http://localhost:7575'
BLOODHOUND_USERNAME = os.environ.get('BLOODHOUND_USERNAME') or 'admin@bloodhound'
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
    with importlib.resources.open_text(data, 'customqueries.json') as file:
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
