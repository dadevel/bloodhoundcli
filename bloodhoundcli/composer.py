import importlib.resources
import json
import os
import re
import subprocess
from pathlib import Path

import click

from bloodhoundcli import data  # type: ignore
from bloodhoundcli import bhce

PROJECT_NAME_PREFIX = 'bloodhound-'
PROJECT_NAME_PATTERN = re.compile(r'^bloodhound-(.*?)_neo4j-data$')
COMPOSE_RESOURCE = importlib.resources.path(data, 'docker-compose.yml')


@click.command(help='List projects')
def list_projects() -> None:
    process = subprocess.run(['podman', 'volume', 'ls', '--format', 'json'], check=True, capture_output=True, text=True)
    volumes = json.loads(process.stdout)
    for volume in volumes:
        if match := PROJECT_NAME_PATTERN.fullmatch(volume['Name']):
            click.echo(match.group(1))


@click.command(help='Create and/or start new project')
@click.argument('name')
def setup_project(name: str) -> None:
    project_name = f'{PROJECT_NAME_PREFIX}{name}'
    with COMPOSE_RESOURCE as composition:
        subprocess.run(
            ['podman', 'compose', '--project-directory', composition.parent, '--project-name', project_name, 'up', '--remove-orphans', '--detach', '--wait'],
            check=True,
            capture_output=False,
        )
    install_custom_queries_bh_legacy()
    bhce.wait_until_up()
    session = bhce.login()
    bhce.import_custom_queries(session)


@click.command(help='Stop project but keep data')
@click.argument('name')
def shutdown_project(name: str) -> None:
    project_name = f'{PROJECT_NAME_PREFIX}{name}'
    with COMPOSE_RESOURCE as composition:
        subprocess.run(
            ['podman', 'compose', '--project-directory', composition.parent, '--project-name', project_name, 'down'],
            check=True,
            capture_output=False,
        )


@click.command(help='Stop project and delete data')
@click.argument('name')
def destroy_project(name: str) -> None:
    project_name = f'{PROJECT_NAME_PREFIX}{name}'
    with COMPOSE_RESOURCE as composition:
        subprocess.run(
            ['podman', 'compose', '--project-directory', composition.parent, '--project-name', project_name, 'down', '--remove-orphans', '--volumes'],
            check=True,
            capture_output=False,
        )


def install_custom_queries_bh_legacy() -> None:
    dest_path = Path.home()/'.config/bloodhound/customqueries.json'
    with importlib.resources.path(data, 'customqueries.json') as src_path:
        if dest_path.resolve() == src_path:
            # queries already installed
            return
        if not dest_path.exists():
            dest_path.parent.mkdir(exist_ok=True)
            os.symlink(src_path, dest_path)
            return
        print('warning: wont install custom queries, there is already a file present')
