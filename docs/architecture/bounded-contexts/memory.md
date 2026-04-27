# Memory

Memory owns long-term memory entries, evidence conflicts, embedding jobs, trajectory records, pattern assets, knowledge nodes, and knowledge edges.

Primary entities span PostgreSQL, Qdrant, and Neo4j. REST APIs expose memory operations through the control plane. Background workers generate embeddings, consolidate memory, and clean sessions.

Memory writes pass through governance and rate-limit checks before persistence.
