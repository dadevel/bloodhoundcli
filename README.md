# bloodhoundcli

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

In any case complete the setup by installing the [custom queries](./customqueries.json) for BloodHound (including queries from [LuemmelSec/Custom-BloodHound-Queries](https://github.com/LuemmelSec/Custom-BloodHound-Queries)).

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

Run a DCSync from [impacket-secretsdump](https://github.com/fortra/impacket) with multiple wordlists and rulesets trough [hashcat](https://github.com/hashcat/hashcat).

~~~ bash
bloodhoundcli db generate-wordlist > ./custom-words.txt  # made of usernames, descriptions, etc.
bloodhoundcli ntds crack ./corp.local.ntds -t ./clem9669-wordlists/dictionnaire_de ./clem9669-hashcat-rules/clem9669_medium.rule -t ./custom-words.txt ./unicorn-hashcat-rules/unicorn\ rules/SuperUnicorn.rule -t ./weakpass-3.txt ./unicorn-hashcat-rules/unicorn\ rules/Unicorn250.rule
~~~

Import the DCSync output and Hashcat potfile into BloodHound (inspired by [knavesec/max](https://github.com/knavesec/max) and [syss-research/hashcathelper](https://github.com/syss-research/hashcathelper)).
This adds `nthash` and `password` properties to users and creates `SharesPasswordWith` edges between users.

~~~ bash
bloodhoundcli ntds import -n ./corp.local.ntds -c ./corp.local.ntds.cleartext -p ./corp.local.ntds.potfile
~~~

Identify pre-created computers by trying to crack their hashes with Hashcat.

~~~ bash
bloodhoundcli ntds pre2k ./corp.local.ntds
~~~

Enrich BloodHound with nodes for standalone computers and local users by leveraging the SQLite database of [crackmapexec](https://github.com/porchetta-industries/crackmapexec).
This includes `nthash` properties from SAM dumps and `AdminTo` as well as `SharesPasswordWith` edges e.g. to identify local admin password reuse.

~~~ bash
bloodhoundcli cme import ~/.cme/workspaces/default/smb.db
~~~

Enrich BloodHound with historical session data as well as inferred RDP and local admin edges (original idea from [this blog post](https://medium.com/@rantasec/bloodhound-for-blue-teams-windows-event-id-4624-a259c76ee09e)).
First export recent logons from Windows Event Logs with [Get-RecentLogons.ps1](./Get-RecentLogons.ps1), then transfer the JSON output to your computer and finally import it into Neo4j.

~~~ bash
bloodhoundcli winevent import ./logons.json
~~~
