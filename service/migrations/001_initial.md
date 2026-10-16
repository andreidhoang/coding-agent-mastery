# Initial schema 1

`service.storage.metadata` is the executable SQLAlchemy Core schema. Initialization
creates schema version 1 and its singleton authority row. All runtime mutation
transactions lock this row. SQLite uses `BEGIN IMMEDIATE`; PostgreSQL takes its
row `FOR UPDATE`. Version mismatches fail closed. There is no rolling migration,
old-worker/new-worker compatibility or downgrade claim in this reference release.

Authority-owned JSON records are versioned by the frozen contract and transitions;
the relational primary keys, tenant/task indexes and unique event sequence remain
shared between dialects. JSON rewrites are serialized under the service lock.
