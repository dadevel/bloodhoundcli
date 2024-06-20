import click

from bloodhoundcli import bhce, composer, neo4j, hashcat, netexec, ntds, pwstats, winevent


@click.group()
def main() -> None:
    pass


main.add_command(neo4j.query)
main.add_command(composer.list_projects)
main.add_command(composer.setup_project)
main.add_command(composer.shutdown_project)
main.add_command(composer.destroy_project)
main.add_command(neo4j.generate_wordlist)
main.add_command(neo4j.enrich)
main.add_command(bhce.import_bhce)
main.add_command(hashcat.hashcat_ntds)
main.add_command(hashcat.hashcat_decode)
main.add_command(netexec.import_netexec)
main.add_command(ntds.import_ntds)
main.add_command(pwstats.pwstats)
main.add_command(winevent.import_winevents)


if __name__ == '__main__':
    main()
