import hashlib
import sqlite3

import click

from bloodhoundcli.db import execute, find_shared_passwords

@click.group()
def cme() -> None:
    pass


@cme.command('import')
@click.argument('cmedb')
def import_(cmedb: str) -> None:
    with sqlite3.connect(cmedb) as db:
        print('importing credentials and admin relations...')
        cursor = db.execute('SELECT u.domain, u.username, u.password, u.credtype, h.hostname, h.domain, h.os FROM users AS u, hosts AS h, admin_relations AS a WHERE u.id=a.userid AND a.hostid=h.id AND NOT u.domain LIKE "%.%"')
        for userdomain, username, secret, credtype, hostname, hostdomain, os in cursor:
            domainuser = '.' in userdomain
            domaincomputer = '.' in hostdomain
            user = f'{username}@{userdomain}'.upper()
            computer = hostname.upper()

            if not domaincomputer:
                execute('MERGE (c:Base:Computer {name: $name}) SET c.objectid=$id, c.enabled=true, c.haslaps=false, c.samaccountname=$accountname, c.standalone=true, c.operatingsystem=$os', id=md5(computer), name=computer, accountname=f'{hostname}$'.upper(), os=os)
            if not domainuser:
                cleartext = credtype == 'plaintext'
                if not cleartext and ':' in secret:
                    _, secret = secret.split(':', maxsplit=1)
                # TODO: calculate nt hash for clear text passwords
                execute('MERGE (u:Base:User {name: $name}) SET u.objectid=$id, u.samaccountname=$accountname, u.local=true, u.' + ('password' if cleartext else 'nthash') + '=$secret', id=md5(user), name=user, accountname=username.upper(), secret=secret)

            if domaincomputer:
                execute('MATCH (u:User {name: $user}) MATCH (c:Computer {name: $computer}) MERGE (u)-[:AdminTo]->(c)', user=user, computer=f'{hostname}.{hostdomain}'.upper())
            else:
                execute('MATCH (u:User {name: $user}) MATCH (c:Computer {name: $computer}) MERGE (u)-[:AdminTo]->(c)', user=user, computer=computer)

        print('importing smb signing status relations...')
        cursor = db.execute('SELECT upper(hostname)||"."||upper(domain), signing FROM hosts WHERE lower(os) LIKE "windows%" AND upper(hostname)<>upper(domain)')
        for computer, signing in cursor:
            execute('MATCH (c:Computer {name: $computer}) SET c.smbsigning=$signing', computer=computer, signing=bool(signing))

    find_shared_passwords()


def md5(value: str) -> str:
    hash = hashlib.new('md5')
    hash.update(value.encode('utf8'))
    return hash.hexdigest()
