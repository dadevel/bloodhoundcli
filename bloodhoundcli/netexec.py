import sqlite3

import click

from bloodhoundcli.neo4j import Database
from bloodhoundcli.util import nthash, md5


@click.command(help='Import local admin data from NetExec smb.db')
@click.argument('smbdb')
def import_netexec(smbdb: str) -> None:
    neo4j = Database.from_env()
    neo4j.create_indices()
    with sqlite3.connect(smbdb) as nxcdb:
        import_computers(nxcdb, neo4j)
        import_users(nxcdb, neo4j)


def import_computers(nxcdb: sqlite3.Connection, neo4j: Database) -> None:
    print('importing computers...')
    cursor = nxcdb.execute('SELECT ip, upper(hostname), upper(domain), os, signing FROM hosts WHERE upper(os) LIKE "WINDOWS%"')
    rows = [pre_process_computer_row(*row) for row in cursor]

    count = sum(neo4j.execute(
        'UNWIND $rows AS row MERGE (c:Base:Computer {name: row[1]}) SET c.reachable=true, c.smbsigning=row[2] RETURN count(c)',
        rows=[row for row in rows if row[0]],
    ))
    print(f'imported {count} domain-joined computers')
    count = sum(neo4j.execute(
        'UNWIND $rows AS row MERGE (c:Base:Computer {name: row[1]}) SET c.objectid=row[2], c.samaccountname=row[3], c.operatingsystem=row[4], c.ipaddress=row[5], c.smbsigning=row[6], c.enabled=true, c.standalone=true, c.reachable=true, c.haslaps=false RETURN count(c)',
        rows=[row for row in rows if not row[0]],
    ))
    print(f'imported {count} standalone computers')


def pre_process_computer_row(ip: str, hostname: str, domain: str, os: str, signing: bool) -> tuple:
    is_domain_joined = '.' in domain
    if is_domain_joined:
        fqdn = f'{hostname}.{domain}'
        return (is_domain_joined, fqdn, signing)
    else:
        fqdn = hostname
        return (is_domain_joined, fqdn, md5(fqdn), f'{hostname}$', os, ip, signing)


def import_users(nxcdb: sqlite3.Connection, neo4j: Database) -> None:
    print('importing users...')
    cursor = nxcdb.execute('SELECT upper(u.domain), upper(u.username), u.password, u.credtype, upper(h.hostname), upper(h.domain), a.hostid=h.id AS isadmin FROM users AS u, hosts AS h, admin_relations AS a WHERE u.id=a.userid')
    local_user_count, admin_edge_count = 0, 0
    for userdomain, username, secret, secret_type, hostname, hostdomain, is_admin in cursor:
        is_domain_user = '.' in userdomain
        is_domain_computer = '.' in hostdomain
        if is_domain_computer:
            fqdn = f'{hostname}.{hostdomain}'
        else:
            fqdn = hostname
        if is_domain_user:
            upn = f'{username}@{userdomain}'
        else:
            upn = f'{username}@{fqdn}'

        if not is_domain_user:
            neo4j.execute('MERGE (u:Base:User {name: $name}) SET u.objectid=$objectid, u.samaccountname=$samaccountname, u.local=true', name=upn, objectid=md5(upn), samaccountname=username)
            local_user_count += 1

        if secret_type == 'plaintext':
            password = secret
            password_hash = nthash(secret)
        elif ':' in secret:
            password = None
            _, password_hash = secret.split(':', maxsplit=1)
        else:
            password = None
            password_hash = secret
        neo4j.execute('MERGE (c:Base:Container:Credential {objectid: $nthash}) SET c.nthash=$nthash, c.password=$password, c.name=coalesce(c.name, $name)', nthash=password_hash, password=password, name='Plain Password' if password else 'NT Hash')
        neo4j.execute('MATCH (u:User {name: $username}) MATCH (c:Credential {objectid: $nthash}) MERGE (u)-[:HasCredential]->(c) MERGE (c)-[:AssignedTo]->(u)', username=upn, nthash=password_hash)

        if is_admin:
            neo4j.execute('MATCH (u:User {name: $username}) MATCH (c:Computer {name: $computername}) MERGE (u)-[:AdminTo]->(c)', username=upn, computername=fqdn)
            admin_edge_count += 1

    print(f'imported {local_user_count} local users and {admin_edge_count} admin relationships')
