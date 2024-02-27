import click

from bloodhoundcli import db, hashcat, netexec, ntds, password_stats, winevent


@click.group()
def main() -> None:
    pass


main.add_command(db.db)
main.add_command(hashcat.hashcat)
main.add_command(netexec.netexec)
main.add_command(ntds.ntds)
main.add_command(password_stats.pwstats)
main.add_command(winevent.winevent)


if __name__ == '__main__':
    main()
