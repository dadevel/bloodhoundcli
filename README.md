# bloodhoundcli

Collection of various utilities to aid in Pentesting with [BloodHound](https://github.com/bloodhoundad/bloodhound).

> **Warning:** This project is work in progress and may be unstable 🚧

# Setup

a) With [pipx](https://github.com/pypa/pipx).

~~~ bash
pipx install git+https://github.com/dadevel/bloodhoundcli.git@main
~~~

b) With [pip](https://github.com/pypa/pip).

~~~ bash
pip install --user git+https://github.com/dadevel/bloodhoundcli.git@main
~~~

In any case complete the setup by installing the [custom queries](./customqueries.json) for BloodHound.

~~~ bash
curl -Lo ~/.config/bloodhound/customqueries.json https://raw.githubusercontent.com/dadevel/bloodhoundcli/main/customqueries.json
~~~

# Usage

Create/destroy a Neo4j container with [podman](https://github.com/containers/podman).
Data is stored in a persistent named volume.

~~~ bash
bloodhoundcli db start project-1
bloodhoundcli db stop project-1
~~~

Execute arbitrary Cypher queries against Neo4j.

~~~ bash
bloodhoundcli db query 'MATCH (u:User {enabled: true} RETURN u.samaccountname)' > ./users.txt
bloodhoundcli db query -s 'MATCH (u:User {name: toUpper($stdin)} SET u.owned=true RETURN count(u)' << EOF
JOHN.DOE@CORP.LOCAL
JANE.DOE@CORP.LOCAL
EOF
~~~

Run the output of [impacket-secretsdump](https://github.com/fortra/impacket) trough [hashcat](https://github.com/hashcat/hashcat) and enrich BloodHound with `nthash` and `password` properties for user nodes.
Also creates `SharesPasswordWith` edges between users.

~~~ bash
bloodhoundcli ntds import -n ./corp.local.ntds -c ./corp.local.ntds.cleartext -p ./corp.local.ntds.potfile
~~~

Enrich BloodHound with nodes for standalone computers and local users by leveraging the SQLite database of [crackmapexec](https://github.com/porchetta-industries/crackmapexec).
This includes `nthash` properties from SAM dumps and `AdminTo` as well as `SharesPasswordWith` edges e.g. to identify local admin password reuse.

~~~ bash
bloodhoundcli cme import ~/.cme/workspaces/default/smb.db
~~~
