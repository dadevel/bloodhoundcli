import click

from bloodhoundcli import cme, db, hashcat, ntds


@click.group()
def main() -> None:
    pass


main.add_command(cme.cme)
main.add_command(db.db)
main.add_command(hashcat.hashcat)
main.add_command(ntds.ntds)


if __name__ == '__main__':
    main()
