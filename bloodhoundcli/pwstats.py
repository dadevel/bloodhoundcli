from bloodhoundcli.neo4j import Database

import click


@click.command(help='Print basic statistics about cracked passwords')
def pwstats() -> None:
    neo4j = Database.from_env()

    total_users = neo4j.execute('MATCH (u:User {enabled: true}) RETURN count(u)')
    cracked_users = neo4j.execute('MATCH (:Credential {cracked: true})-[:AssignedTo]->(u:User {enabled: true}) RETURN count(u)')
    cracked_percentage = round(cracked_users[0] * 100 / total_users[0])
    print(f'cracked passwords: {cracked_users[0]}/{total_users[0]} ({cracked_percentage}%)')
    print()

    print('most used cracked passwords:')
    for line in neo4j.execute('MATCH p = (c:Credential {cracked: true})-[:AssignedTo]->(u:User {enabled: true}) WITH count(u) AS count, c.password AS password RETURN toString(count) + " " + password ORDER BY count DESC LIMIT 10'):
        print(line)
    print()

    print('most used passwords:')
    for count, hash, password in neo4j.execute('MATCH (a:User {enabled: true})-[:HasCredential]->(c:Credential)-[:AssignedTo]->(b:User {enabled: true}) WHERE a<>b WITH c.nthash AS hash, c.password AS password, collect(DISTINCT toLower(b.name)) AS users WHERE size(users) > 1 RETURN [size(users), hash, password] ORDER BY size(users) DESC LIMIT 10'):
        print(count, hash, password or '')
    print()
