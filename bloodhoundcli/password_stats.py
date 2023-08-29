from bloodhoundcli.db import query

import click


@click.command()
def cli_pwstats() -> None:
    print('top 10 most used passwords:')
    for line in query('MATCH (u:User {enabled: true}) WITH count(u.password) AS pwcount, u.password AS pw RETURN (toString(pwcount) + " " + pw) ORDER BY pwcount DESC LIMIT 10'):
        print(line)

    print('password reuse clusters:')
    for count, hash, password, users in query('MATCH p = (a:User {enabled: true})-[:SharesPasswordWith]-(b:User {enabled: true}) WHERE a<>b WITH a.nthash AS hash, collect(DISTINCT b.password) AS passwords, collect(DISTINCT toLower(b.name)) AS users WHERE size(users) > 1 RETURN [size(users), hash, passwords[0], users] ORDER BY size(users) DESC LIMIT 10'):
        print(count, hash, password or 'null', ' '.join(users))
