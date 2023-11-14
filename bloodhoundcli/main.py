import click

from bloodhoundcli import cme, db, hashcat, logons, ntds, password_stats


@click.group()
def main() -> None:
    pass


main.add_command(cme.cme)
main.add_command(db.db)
main.add_command(hashcat.hashcat)
main.add_command(logons.logons)
main.add_command(ntds.ntds)
main.add_command(password_stats.pwstats)


if __name__ == '__main__':
    main()
