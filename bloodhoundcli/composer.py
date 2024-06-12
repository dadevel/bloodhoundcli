import importlib.resources
import json
import subprocess

import click

from bloodhoundcli import data  # type: ignore

PROJECT_NAME_PREFIX = 'bloodhound-'
COMPOSE_RESOURCE = importlib.resources.path(data, 'docker-compose.yml')


@click.command(help='List projects')
def list_projects() -> None:
    process = subprocess.run(['podman', 'compose', 'ls', '--all', '--format', 'json'], check=True, capture_output=True, text=True)
    projects = json.loads(process.stdout)
    for project in projects:
        if project['Name'].startswith(PROJECT_NAME_PREFIX):
            click.echo(f'{project["Name"].removeprefix(PROJECT_NAME_PREFIX)} {project["Status"]}')


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
