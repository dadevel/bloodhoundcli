FROM docker.io/library/neo4j:4.4.12
# apoc version from https://neo4j-contrib.github.io/neo4j-apoc-procedures/versions.json
RUN wget -qO /var/lib/neo4j/plugins/apoc.jar https://github.com/neo4j-contrib/neo4j-apoc-procedures/releases/download/4.4.0.11/apoc-4.4.0.11-all.jar
# gds version from https://graphdatascience.ninja/versions.json
RUN wget -qO /var/lib/neo4j/plugins/gds.jar https://graphdatascience.ninja/neo4j-graph-data-science-2.2.3.jar
RUN echo 'dbms.security.procedures.unrestricted=apoc.*,gds.*' >> /var/lib/neo4j/conf/neo4j.conf && \
echo 'dbms.security.procedures.allowlist=apoc.*,gds.*' >> /var/lib/neo4j/conf/neo4j.conf
