"""Schema 1 -> 2: unambiguous tenant identities and a writer compatibility gate.

Quiesce all writers and take a verified backup before invoking this migration.
The gate catches obsolete writers; it is not a security capability or a rolling
upgrade protocol. The transaction preserves public IDs and all evidence bytes.
"""

from __future__ import annotations

import argparse
import json
import os

import sqlalchemy as sa
from ..artifacts import digest_json
from ..contracts import Conflict, Unsupported

SCHEMA_VERSION = 2


def record_key(tenant_id: str, logical_id: str) -> str:
    return digest_json([tenant_id, logical_id])


def register_sqlite_protocol(dbapi) -> None:
    # A schema-1 connection has no such function, so guarded writes fail closed.
    dbapi.create_function("cam_writer_schema", 0, lambda: SCHEMA_VERSION)


def set_writer_protocol(connection) -> None:
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql("SET LOCAL cam.writer_schema = '2'")


def install_writer_fences(connection, tables) -> None:
    """Guard every authority-owned DML table, including the version row itself."""
    names = [table.name for table in tables]
    if connection.dialect.name == "sqlite":
        for name in names:
            for operation in ("INSERT", "UPDATE", "DELETE"):
                trigger = f"cam_v2_{name}_{operation.lower()}"
                connection.exec_driver_sql(
                    f'CREATE TRIGGER IF NOT EXISTS "{trigger}" BEFORE {operation} ON "{name}" '
                    "WHEN cam_writer_schema() IS NOT 2 "
                    "BEGIN SELECT RAISE(ABORT, 'schema 2 writer protocol required'); END"
                )
    elif connection.dialect.name == "postgresql":
        connection.exec_driver_sql("""
            CREATE OR REPLACE FUNCTION cam_require_writer_v2() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF current_setting('cam.writer_schema', true) IS DISTINCT FROM '2' THEN
                    RAISE EXCEPTION 'schema 2 writer protocol required';
                END IF;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END; $$
        """)
        for name in names:
            trigger = f"cam_v2_{name}"
            connection.exec_driver_sql(f'DROP TRIGGER IF EXISTS "{trigger}" ON "{name}"')
            connection.exec_driver_sql(
                f'CREATE TRIGGER "{trigger}" BEFORE INSERT OR UPDATE OR DELETE ON "{name}" '
                "FOR EACH ROW EXECUTE FUNCTION cam_require_writer_v2()"
            )
    else:
        raise Unsupported("migration supports only SQLite and PostgreSQL")


def migrate_v1_to_v2(url: str) -> dict:
    """Explicit atomic migration. Never called automatically by RuntimeStore."""
    from ..storage import authority, schema_versions, event_rows, TABLES

    engine = sa.create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @sa.event.listens_for(engine, "connect")
        def sqlite_connection(dbapi, _):
            register_sqlite_protocol(dbapi)
            dbapi.execute("PRAGMA busy_timeout=30000")

    try:
        with engine.connect() as c:
            if c.dialect.name == "sqlite":
                c.exec_driver_sql("BEGIN IMMEDIATE")
            elif c.dialect.name == "postgresql":
                c.begin()
            else:
                raise Unsupported("migration supports only SQLite and PostgreSQL")
            try:
                # Authority lock serializes against transactions from schema 1.
                c.execute(sa.select(authority.c.id).where(authority.c.id == 1).with_for_update()).scalar_one()
                versions = c.execute(sa.select(schema_versions.c.version)).scalars().all()
                if versions != [1]:
                    raise Unsupported("migration requires exactly schema 1")
                set_writer_protocol(c)
                converted = {}
                for name, field in (("dispatches", "dispatch_id"), ("candidates", "candidate_id")):
                    table = TABLES[name]
                    rows = [dict(row) for row in c.execute(sa.select(table)).mappings()]
                    replacements = []
                    keys = set()
                    for row in rows:
                        data = row["data"]
                        tenant = row["tenant_id"]
                        logical_id = data.get(field)
                        if (
                            not isinstance(logical_id, str)
                            or data.get("tenant_id") != tenant
                            or data.get("task_id") != row["task_id"]
                        ):
                            raise Conflict("legacy identity row does not match its tenant/task binding")
                        if row["id"] != tenant + ":" + logical_id:
                            raise Conflict("legacy identity key does not match schema 1")
                        key = record_key(tenant, logical_id)
                        if key in keys:
                            raise Conflict("legacy rows have duplicate canonical identity")
                        keys.add(key)
                        replacements.append({**row, "id": key})
                    # Delete/insert within the same transaction also handles a new
                    # key that happens to equal another old key without orphaning.
                    c.execute(table.delete())
                    if replacements:
                        c.execute(table.insert(), replacements)
                    converted[name] = len(replacements)
                c.execute(schema_versions.delete())
                c.execute(schema_versions.insert().values(version=SCHEMA_VERSION))
                install_writer_fences(c, [schema_versions, authority, event_rows, *TABLES.values()])
                c.commit()
                return {
                    "from_version": 1,
                    "to_version": SCHEMA_VERSION,
                    "converted": converted,
                    "writer_gate": "compatibility only; explicit quiescence required",
                }
            except BaseException:
                c.rollback()
                raise
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Offline authority schema 1 to 2 migration")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="disposable copy or explicitly backed-up authority URL")
    source.add_argument("--url-env", help="name of environment variable containing the authority URL")
    args = parser.parse_args()
    url = args.url
    if args.url_env:
        url = os.environ.get(args.url_env)
        if not url:
            parser.error("the named URL environment variable is unset or empty")
    print(json.dumps(migrate_v1_to_v2(url), sort_keys=True))


if __name__ == "__main__":
    main()
