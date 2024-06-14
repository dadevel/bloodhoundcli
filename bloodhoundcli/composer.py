import importlib.resources
import json
import re
import subprocess

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
