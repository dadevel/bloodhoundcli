import click

from bloodhoundcli import neo4j, hashcat, netexec, ntds, pwstats, winevent


@click.group()
def main() -> None:
    pass


@main.command(help='Execute Cypher statement')
@click.argument('statement')
@click.option('-s', '--stdin', is_flag=True)
def query(statement: str, stdin: bool) -> None:
    neo4j.query(statement, stdin)


main.add_command(neo4j.neo4j_list)
main.add_command(neo4j.neo4j_setup)
main.add_command(neo4j.neo4j_delete)
main.add_command(neo4j.neo4j_enrich)
#main.add_command(neo4j.import_sharphound)  # work in progress
main.add_command(neo4j.generate_wordlist)
main.add_command(hashcat.hashcat_ntds)
main.add_command(hashcat.hashcat_decode)
main.add_command(netexec.import_netexec)
main.add_command(ntds.import_ntds)
main.add_command(pwstats.pwstats)
main.add_command(winevent.import_winevents)


if __name__ == '__main__':
    main()
