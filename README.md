# BloodHoundCli

![Screenshot](./assets/demo.png)

Collection of various utilities to aid in Pentesting with [BloodHound](https://github.com/bloodhoundad/bloodhound).

# Setup

1. Install [Podman](https://github.com/containers/podman/) and [docker-compose](https://github.com/docker/compose).
2. [Configure rootless containers](https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md) for Podman.
3. Enable the Podman socket for your user.

    ~~~ bash
    systemctl --user enable --now podman.socket
    ~~~

3. Install this Python package with [pipx](https://github.com/pypa/pipx).

    ~~~ bash
    pipx install git+https://github.com/dadevel/bloodhoundcli.git@main
    ~~~

## Custom Queries

If you don't want to use BloodHoundCli and are here just for the [custom queries](./bloodhoundcli/data/customqueries.json) run the command below.
Otherwise the queries are automatically installed when you create your first BloodHoundCli project.

~~~ bash
curl -Lo ~/.config/bloodhound/customqueries.json https://github.com/dadevel/bloodhoundcli/raw/main/bloodhoundcli/data/customqueries.json
~~~

The queries are based on work by [@luemmelsec](https://github.com/LuemmelSec/Custom-BloodHound-Queries) and [@martinsohn](https://gist.github.com/martinsohn/3f6122c7486ca3ffcaa444772f1a35f2).
Thank you!

## Project Management

Projects are managed with [Podman](https://github.com/containers/podman) containers.
Only one project can be active at a time.
Each project consists of [BloodHound Community Edition](https://github.com/specterops/bloodhound), Neo4j and Postgres.

~~~ bash
bloodhoundcli setup-project example1
bloodhoundcli shutdown-project example1
bloodhoundcli setup-project example2
bloodhoundcli list-projects
bloodhoundcli destroy-project example1
bloodhoundcli destroy-project example2
~~~

## Authentication

- BloodHound Legacy: <bolt://localhost:7687/>, username *neo4j*, empty password
- Neo4j: <http://localhost:7474/>, username *neo4j*, empty password
- BloodHound Community Edition: <http://localhost:7575/>, username *admin@bloodhound*, empty password

## Data Collection

- [SharpHound](https://github.com/bloodhoundad/sharphound): must be imported via BloodHound Community Edition
- [AzureHound](https://github.com/bloodhoundad/azurehound): must be import via BloodHound Community Edition
- [bloodhound.py](https://github.com/dirkjanm/bloodhound.py): can be imported with Legacy BloodHound

## CLI Integration

Quickly fetch data from Neo4j for use with other tools or import data from other tools into BloodHound.

~~~ bash
bloodhoundcli query 'MATCH (u:User {enabled: true}) RETURN u.samaccountname' > ./users.txt
bloodhoundcli query -s 'MATCH (u:User {name: toUpper($stdin)} SET u.owned=true RETURN u.name' << EOF
john.doe@corp.local
jane.doe@corp.local
EOF
bloodhoundcli query -s -j 'MATCH (u:User {name: $stdin.name}) SET u.foo=$stdin.value RETURN u.name' << EOF
{"name": "john.doe@corp.local", "value": "bar"}
{"name": "jane.doe@corp.local", "value": "baz"}
EOF
~~~

## NTDS Import

Run a DCSync from [impacket-secretsdump](https://github.com/fortra/impacket) with multiple wordlists and rulesets trough [Hashcat](https://github.com/hashcat/hashcat).
LM hashes and pre-created computer accounts are automatically cracked unless `--no-lm-brute` respective `--no-pre2k` is specified.

~~~ bash
impacket-secretsdump -just-dc -outputfile corp.local -k -no-pass dc01.corp.local
bloodhoundcli generate-wordlist > ./custom-words.txt  # made of usernames, descriptions, etc.
bloodhoundcli hashcat-ntds -t ./clem9669-wordlists/dictionnaire_de ./clem9669-hashcat-rules/clem9669_medium.rule -t ./custom-words.txt ./unicorn-hashcat-rules/unicorn\ rules/SuperUnicorn.rule -t ./weakpass-3.txt ./unicorn-hashcat-rules/unicorn\ rules/Unicorn250.rule -p ./hashcat.potfile ./*.ntds
~~~

Import the DCSync output and Hashcat potfile into BloodHound (inspired by [@knavesec](https://github.com/knavesec/max) and [@syss-research](https://github.com/syss-research/hashcathelper)).
This adds `Credential` objects with `nthash`, `lmhash` and `password` properties and `HasCredential` as well as `AssignedTo` edges between users and credentials.

~~~ bash
bloodhoundcli import-ntds -p ./hashcat.potfile ./*.ntds
~~~

> **Note:**
> `bloodhoundcli` assumes that the name of the NTDS file minus the `.ntds` suffix is the FQDN of the domain.
> This means a DCSync from `dc01.subdomain.corp.local` should be named `subdomain.corp.local.ntds`.

## NetExec Integration

Import nodes for standalone computers and local users by leveraging the SQLite database of [NetExec](https://github.com/pennyw0rth/netexec).
This includes `nthash` properties from SAM dumps and `AdminTo` as well as `HasCredential` and `AssignedTo` edges e.g. to identify local admin password reuse.

~~~ bash
bloodhoundcli import-netexec ~/.nxc/workspaces/default/smb.db
~~~

## Manual Session Collection

Add historical session data as well as inferred RDP and local admin edges (original idea from [@rantasec](https://medium.com/@rantasec/bloodhound-for-blue-teams-windows-event-id-4624-a259c76ee09e)).
First export recent logons from Windows Event Logs with [Get-RecentLogons.ps1](./Get-RecentLogons.ps1), then transfer the JSON output to your computer and finally import it into Neo4j.

~~~ bash
bloodhoundcli import-winevents ./logons.json
~~~

## Weighted Graph

Assign weights to edges in BloodHound (based on work by [@riccardoancarani](https://riccardoancarani.github.io/2019-11-08-not-all-paths-are-equal/) and [@jmbesnard](https://www.linkedin.com/pulse/graph-theory-assess-active-directory-smartest-vs-shortest-besnard-0qgle)).

~~~ bash
bloodhoundcli enrich
~~~

Now you can use queries like the following to find the easiest instead of the shortest path to Domain Admin.

~~~ cypher
MATCH (a {owned: true}) MATCH (b {highvalue: true}) CALL apoc.algo.dijkstra(a, b, '>', 'cost') YIELD path RETURN path;
~~~
