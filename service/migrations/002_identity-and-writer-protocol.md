# Offline schema 1 → 2 migration

Schema 1 concatenated tenant and logical ID with `:` for dispatch/candidate primary
keys. Valid IDs containing `:` can alias. Schema 2 uses the SHA-256 of canonical
JSON `[tenant_id, logical_id]`, retaining the public IDs, tenant/task bindings,
immutable record contents, liabilities, artifact references, events and cursors.

`RuntimeStore` initializes fresh databases at schema 2 and refuses existing schema
1 or unknown versions. It does **not** silently upgrade a historical database.
Before upgrading an authoritative database, stop all controllers/relays/workers,
confirm quiescence, take a verified recoverable backup, and test a disposable copy.
Run the explicit migration against that copy first:

```sh
python -m service.migrations.v2_identity --url sqlite:////absolute/path/disposable-copy.sqlite
```

For an operator-authorized PostgreSQL database, pass its configured SQLAlchemy URL;
keep credentials out of saved logs. After validating the migrated copy, repeat the
same migration only against the explicitly backed-up authoritative database and
restart **all** writers on schema-2 code. Check task snapshots, liabilities,
artifacts and an idempotent receipt before reopening admission. Rollback means
restoring the verified backup while all writers remain stopped; there is no
in-place downgrade or mixed-version rolling upgrade.

The migration holds `BEGIN IMMEDIATE` on SQLite or the singleton authority row
`FOR UPDATE` on PostgreSQL. It validates legacy bindings, rewrites both sets of
private keys, advances the version and installs all writer guards in one atomic
transaction. A failure rolls back keys, version and guards. Unknown versions and
malformed legacy rows abort without making a partial migration.

SQLite DML guards require the schema-2 connection function; PostgreSQL DML guards
require the transaction-local schema-2 setting. Legacy connections/constructors
lack this protocol and cannot mutate even the version table after migration. This
is a **compatibility gate**, not a security capability: trusted SQL users can set
or bypass it. It supplements explicit quiescence; it never authorizes a rolling
upgrade, hostile-tenant isolation or restoration of external effects.

A collision already prevented or lost under schema 1 cannot be reconstructed by
this migration. The surviving rows are preserved; unavailable historical effects
need operation-specific reconciliation. Tests create schema-1 fixtures in temporary
paths, migrate disposable copies, verify the original copy's digest and exercise
rollback plus rejection of an already-open legacy writer on SQLite and PostgreSQL.

Concurrent initialization of an already-created empty PostgreSQL schema is
serialized by a schema-scoped transaction advisory bootstrap lock, then the
inserted authority row lock and a fresh version read. Existing schemas do not
reinstall trigger DDL on each open. Initial `create_all` of a totally new schema
still requires one initializer or operator-precreated metadata; concurrent fresh
schema DDL is outside this reference's bootstrap contract.

An absent version table or an empty version table is allowed only when **every**
authority-owned table is entirely empty. Populated unversioned databases fail
before initialization DDL/DML, with a second emptiness check under bootstrap
serialization. Do not infer or repair their version: preserve the database and
investigate its provenance through separately authorized operator recovery.

For PostgreSQL credential-bearing URLs, obtain the configured value through a
secret-aware environment and pass only its variable name, avoiding URL credentials
in process arguments:

```sh
python -m service.migrations.v2_identity --url-env CAM_MIGRATION_URL
```

The command fails if that variable is absent or empty. It prints only migration
counts/version, never the configured URL.
