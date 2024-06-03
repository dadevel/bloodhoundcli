# bloodhoundcli

![Screenshot](./assets/demo.png)

Collection of various utilities to aid in Pentesting with [BloodHound](https://github.com/bloodhoundad/bloodhound).

# Setup

a) With [pipx](https://github.com/pypa/pipx).

~~~ bash
pipx install git+https://github.com/dadevel/bloodhoundcli.git@main
~~~

b) With [pip](https://github.com/pypa/pip).

~~~ bash
pip install --user git+https://github.com/dadevel/bloodhoundcli.git@main
~~~

In any case complete the setup by installing the [custom queries](./customqueries.json) for BloodHound (includes queries from [@luemmelsec](https://github.com/LuemmelSec/Custom-BloodHound-Queries) and [@martinsohn](https://gist.github.com/martinsohn/3f6122c7486ca3ffcaa444772f1a35f2) among others).

~~~ bash
curl -Lo ~/.config/bloodhound/customqueries.json https://raw.githubusercontent.com/dadevel/bloodhoundcli/main/customqueries.json
~~~

# Usage

Run Neo4j containers with [Podman](https://github.com/containers/podman).

~~~ bash
bloodhoundcli setup project-1
bloodhoundcli setup project-2  # first container will be stopped
~~~

Execute arbitrary Cypher queries against Neo4j.

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

Run a DCSync from [impacket-secretsdump](https://github.com/fortra/impacket) with multiple wordlists and rulesets trough [Hashcat](https://github.com/hashcat/hashcat).
Pre-created computer accounts are automatically cracked.
Specify `--no-lm-brute` to skip LM hash cracking.

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

Import nodes for standalone computers and local users by leveraging the SQLite database of [NetExec](https://github.com/pennyw0rth/netexec).
This includes `nthash` properties from SAM dumps and `AdminTo` as well as `HasCredential` and `AssignedTo` edges e.g. to identify local admin password reuse.

~~~ bash
bloodhoundcli import-netexec ~/.nxc/workspaces/default/smb.db
~~~

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

## BloodHound Community Edition

Setup BHCE in Podman.

~~~ bash
systemctl --user enable --now podman.socket
export DOCKER_HOST="unix:///run/user/$UID/podman/podman.sock"
podman compose up -d
firefox http://localhost:7575/
~~~

Login to BHCE at <http://localhost:7575> with username *admin@bloodhound* and the initial password from the logs.

~~~ bash
podman compose logs bloodhound 2> /dev/null | grep -oE 'Initial Password Set To: *[^ ]+' | sed 's|Initial Password Set To: *||'
~~~

Login to Neo4j at <http://localhost:7474/> with the credentials *neo4j:bloodhound*.
