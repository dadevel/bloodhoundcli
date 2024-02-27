from bloodhoundcli.db import Database

import click


@click.command()
def pwstats() -> None:
    neo4j = Database.from_env()

    print('most used cracked passwords:')
    for line in neo4j.execute('MATCH p = (c:Credential {cracked: true})-[:AssignedTo]->(u:User {enabled: true}) WITH count(u) AS count, c.password AS password RETURN toString(count) + " " + password ORDER BY count DESC LIMIT 10'):
        print(line)
    print()

    print('most used passwords:')
    for count, hash, password in neo4j.execute('MATCH (a:User {enabled: true})-[:HasCredential]->(c:Credential)-[:AssignedTo]->(b:User {enabled: true}) WHERE a<>b WITH c.nthash AS hash, c.password AS password, collect(DISTINCT toLower(b.name)) AS users WHERE size(users) > 1 RETURN [size(users), hash, password] ORDER BY size(users) DESC LIMIT 10'):
        print(count, hash, password or '')
    print()
