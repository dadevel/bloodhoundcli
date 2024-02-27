MATCH ()-[r]->() DELETE r;
MATCH (x) DELETE x;

MERGE (c:Base:Computer {name: 'SRV01.CORP.LOCAL'}) SET c.objectid='e18fbf36-28bd-4940-aebd-18d9b3012d86', c.enabled=true, c.haslaps=false, c.samaccountname='SRV01$';
MERGE (u:Base:User {name: 'JANE.ADM@CORP.LOCAL'}) SET u.objectid='36c64e3f-355a-4d5b-a705-2493028efffd', u.samaccountname='JANE.ADM$';
MATCH (u:User {name: 'JANE.ADM@CORP.LOCAL'}) MATCH (c:Computer {name: 'SRV01.CORP.LOCAL'}) MERGE (c)-[:HasSession]->(u);
MERGE (u:Base:User {name: 'JOHN.DOE@CORP.LOCAL'}) SET u.objectid='1c9ebd24-26d6-427d-bf34-ed99f9f97a81', u.samaccountname='JOHN.DOE$', u.owned=true;
MATCH (u:User {name: 'JOHN.DOE@CORP.LOCAL'}) MATCH (c:Computer {name: 'SRV01.CORP.LOCAL'}) MERGE (u)-[:CanRDP]->(c);
MERGE (g:Base:Group {name: 'HELPDESK@CORP.LOCAL'}) SET g.objectid='31ef67bf-dfd0-4552-8ce3-e1fa0c54b778';
MATCH (u:User {name: 'JOHN.DOE@CORP.LOCAL'}) MATCH (g:Group {name: 'HELPDESK@CORP.LOCAL'}) MERGE (u)-[:MemberOf]->(g);
MERGE (g:Base:Group {name: 'DOMAIN ADMINS@CORP.LOCAL'}) SET g.objectid='c0ac5c69-3619-4926-948a-88f36330ac57', g.highvalue=true;
MATCH (u:User {name: 'JANE.ADM@CORP.LOCAL'}) MATCH (g:Group {name: 'DOMAIN ADMINS@CORP.LOCAL'}) MERGE (u)-[:MemberOf]->(g);
MERGE (c:Base:Computer {name: 'SRV02.CORP.LOCAL'}) SET c.objectid='99f2952c-cc91-4063-bcf1-3ca04853257c', c.enabled=true, c.haslaps=true, c.samaccountname='SRV02$';
MATCH (g:Group {name: 'HELPDESK@CORP.LOCAL'}) MATCH (c:Computer {name: 'SRV02.CORP.LOCAL'}) MERGE (g)-[:ReadLAPSPassword]->(c);
MERGE (g:Base:Group {name: 'TRUSTED SYSTEMS@CORP.LOCAL'}) SET g.objectid='9c52d2c9-5c6a-4ef2-8e4c-66cc9abfab62';
MATCH (c:Computer {name: 'SRV02.CORP.LOCAL'}) MATCH (g:Group {name: 'TRUSTED SYSTEMS@CORP.LOCAL'}) MERGE (c)-[:MemberOf]->(g);
MATCH (g1:Group {name: 'TRUSTED SYSTEMS@CORP.LOCAL'}) MATCH (g2:Group {name: 'DOMAIN ADMINS@CORP.LOCAL'}) MERGE (g1)-[:GenericWrite]->(g2);
MERGE (o:Base:OU {name: 'USERS@CORP.LOCAL'}) SET o.objectid='93f247b5-99ad-47a8-a5ef-b994562a0cb7';
MATCH (u:User {name: 'JOHN.DOE@CORP.LOCAL'}) MATCH (o:OU {name: 'USERS@CORP.LOCAL'}) MERGE (o)-[:Contains]->(u);
MATCH (u:User {name: 'JANE.ADM@CORP.LOCAL'}) MATCH (o:OU {name: 'USERS@CORP.LOCAL'}) MERGE (o)-[:Contains]->(u);

MATCH p=(n {owned: true})-[*1..]->(m {highvalue: true}) RETURN p;
MATCH p=allShortestPaths((n {owned: true})-[*1..]->(m {highvalue: true})) RETURN p;
MATCH (a {owned: true}) MATCH (b {highvalue: true}) CALL apoc.algo.dijkstra(a, b, '>', 'cost') YIELD path RETURN path;
