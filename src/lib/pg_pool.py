#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS: pg_pool
  Shared PostgreSQL connection pool manager for 08-Squad-Agent.
  Ensures dynamic creation of the obsidiandb database and manages thread-safe pool instances.

DATA FLOW:
  1. Input:   Configuration settings and logging context.
  2. Logic:   Establishes connection to 'postgres', checks/creates database,
              initializes ThreadedConnectionPool.
  3. Output:  Active connection pool singleton instance.

KEY PARAMETERS:
  - config:   Shared configuration singleton.
  - logger:   UniLog logging engine singleton.
"""

import atexit
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from psycopg2.pool import ThreadedConnectionPool as pgThreadedConnectionPool
    import psycopg2 as pgConnection
    HAS_POSTGRES = True
except ImportError:
    pgThreadedConnectionPool = None
    pgConnection = None
    HAS_POSTGRES = False

_pool_instance: Optional[Any] = None

# -----------------------------------------------------------------------------------------------

def get_pg_pool(*, config: Any, logger: Any) -> Optional[Any]:
    """
    Retrieves the shared ThreadedConnectionPool instance, lazily initializing it.
    """
    global _pool_instance
    if _pool_instance is not None:
        return _pool_instance

    if not HAS_POSTGRES:
        logger.warning("SharedPool : psycopg2-binary is not installed in the active environment.")
        return None

    # Retrieve database configurations via standard dynamic address accessor (zero silent fallback)
    try:
        db_addr = config.get_listen_addr("timescale_db")
        host, port_str = db_addr.split(":")
        port = int(port_str)
    except Exception as e:
        logger.warning(f"SharedPool : Failed to resolve capability 'timescale_db' listen address ({e}).")
        return None

    timescale_db = config.data.get("capabilities", {}).get("timescale_db", {})
    user = timescale_db.get("user")
    password = timescale_db.get("password")
    if not user or not password:
        logger.warning("SharedPool : Missing required database credentials in capability 'timescale_db'.")
        return None
    db_name = "obsidiandb"

    # Decrypt password if supported
    if hasattr(config, "decrypt_secret"):
        try:
            password = config.decrypt_secret(password)
        except Exception as e:
            logger.warning("SharedPool : Decrypting password failed: {0}".format(e))

    logger.info("SharedPool : Connecting to {0}:{1} (database={2})".format(host, port, db_name))

    # Ensure database exists dynamically
    try:
        conn_postgres = pgConnection.connect(
            host=host,
            port=port,
            dbname="postgres",
            user=user,
            password=password,
            connect_timeout=3
        )
        conn_postgres.autocommit = True
        with conn_postgres.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if not cursor.fetchone():
                logger.info("SharedPool : Database '{0}' not found. Creating dynamically...".format(db_name))
                cursor.execute("CREATE DATABASE {0}".format(db_name))
        conn_postgres.close()
    except Exception as e:
        logger.warning("SharedPool : Database check/creation check failed: {0}".format(e))

    # Initialize connection pool
    try:
        _pool_instance = pgThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=host,
            port=port,
            dbname=db_name,
            user=user,
            password=password,
            connect_timeout=5
        )
        atexit.register(close_pg_pool)
        return _pool_instance
    except Exception as e:
        logger.error("SharedPool : Failed to initialize ThreadedConnectionPool: {0}".format(e))
        return None

# -----------------------------------------------------------------------------------------------

def close_pg_pool() -> None:
    """Closes all active connections in the pool on shutdown."""
    global _pool_instance
    if _pool_instance:
        try:
            _pool_instance.closeall()
        except Exception:
            pass
        _pool_instance = None


# -----------------------------------------------------------------------------------------------

def resolve_schema_name(script_file: str) -> str:
    """
    Dynamically resolves the schema name by tracing the executing script file path.
    Walks up the path hierarchy to find the repository root directory name.
    """
    path = Path(script_file).resolve()
    target_repos = ["08-Squad-Agent", "01-Strategic-Nexus", "09-RAG-Engine", "watchdog-agent"]
    for parent in [path] + list(path.parents):
        if parent.name in target_repos:
            return parent.name
    return path.parent.name


# -----------------------------------------------------------------------------------------------

FLEET_ERROR_DDL = """CREATE SCHEMA IF NOT EXISTS watchdog_agent;

CREATE TABLE IF NOT EXISTS watchdog_agent.fleet_error_logs (
    timestamp     TIMESTAMPTZ NOT NULL,
    brain_id      VARCHAR(64) NOT NULL,
    hostname      VARCHAR(64) NOT NULL,
    service_name  VARCHAR(64) NOT NULL,
    logger_name   VARCHAR(64) NOT NULL,
    level         SMALLINT NOT NULL,
    level_str     VARCHAR(16) NOT NULL,
    filename      VARCHAR(256),
    function_name VARCHAR(128),
    line_number   VARCHAR(16),
    message       TEXT NOT NULL,
    stack_trace   TEXT,
    event_hash    CHAR(64) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (timestamp, event_hash)
);

CREATE TABLE IF NOT EXISTS watchdog_agent.fleet_incidents (
    incident_id         VARCHAR(128) PRIMARY KEY,
    brain_id            VARCHAR(64) NOT NULL,
    event_hash          CHAR(64) NOT NULL DEFAULT '',
    service_name        VARCHAR(64) NOT NULL,
    hostname            VARCHAR(64) NOT NULL DEFAULT '',
    level_str           VARCHAR(16) NOT NULL DEFAULT 'ERROR',
    tier                SMALLINT NOT NULL,
    status              VARCHAR(32) NOT NULL,
    filename            VARCHAR(256) DEFAULT '',
    line_number         VARCHAR(16) DEFAULT '',
    message             TEXT NOT NULL,
    root_cause          TEXT DEFAULT '',
    proposed_patch      TEXT DEFAULT '',
    target_relpath      VARCHAR(512) DEFAULT '',
    verification_output TEXT DEFAULT '',
    action_taken        TEXT DEFAULT '',
    occurrence_count    INTEGER NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fleet_incidents_brain_status
    ON watchdog_agent.fleet_incidents (brain_id, status, updated_at DESC);"""


@contextmanager
def _borrow_conn(pg_pool: Any, *, commit: bool = False):
    """Borrows a connection from pg_pool, rolling back cleanly on failure."""
    conn = pg_pool.getconn()
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception:
        with suppress(Exception):
            conn.rollback()
        raise
    finally:
        pg_pool.putconn(conn)


def ensure_fleet_error_schema(pg_pool: Any, logger: Any) -> bool:
    """Ensures Option B schema 'watchdog_agent' and triage tables exist in obsidiandb."""
    if not pg_pool:
        return False
    try:
        with _borrow_conn(pg_pool, commit=True) as conn:
            with conn.cursor() as cursor:
                cursor.execute(FLEET_ERROR_DDL)
        return True
    except Exception as e:
        logger.warning(f"SharedPool : Could not verify watchdog_agent schema ({e}).")
        return False


# -----------------------------------------------------------------------------------------------

def query_recent_fleet_errors(
    pg_pool: Any,
    logger: Any,
    *,
    brain_id: str,
    service_name: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Fetches recent ERROR/CRITICAL entries for a service partitioned by brain_id."""
    if not pg_pool:
        return []
    try:
        with _borrow_conn(pg_pool) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT timestamp, hostname, level_str, filename, function_name, line_number, message, stack_trace, event_hash
                    FROM watchdog_agent.fleet_error_logs
                    WHERE brain_id = %s AND service_name = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (brain_id, service_name, limit),
                )
                rows = cursor.fetchall()
        return [
            {
                "timestamp": r[0].isoformat() if r[0] else "",
                "hostname": r[1] or "",
                "level_str": r[2] or "",
                "filename": r[3] or "",
                "function_name": r[4] or "",
                "line_number": r[5] or "",
                "message": r[6] or "",
                "stack_trace": r[7] or "",
                "event_hash": r[8] or "",
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"SharedPool : Failed querying fleet_error_logs ({e}).")
        return []


# -----------------------------------------------------------------------------------------------

def upsert_fleet_incident(pg_pool: Any, logger: Any, record: Dict[str, Any]) -> bool:
    """Persists or updates an AutoRepair triage incident record in PostgreSQL."""
    if not pg_pool:
        return False
    try:
        with _borrow_conn(pg_pool, commit=True) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO watchdog_agent.fleet_incidents (
                        incident_id, brain_id, event_hash, service_name, hostname, level_str,
                        tier, status, filename, line_number, message, root_cause, proposed_patch,
                        target_relpath, verification_output, action_taken, occurrence_count, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, NOW()
                    )
                    ON CONFLICT (incident_id) DO UPDATE SET
                        tier = EXCLUDED.tier,
                        status = EXCLUDED.status,
                        root_cause = EXCLUDED.root_cause,
                        proposed_patch = EXCLUDED.proposed_patch,
                        target_relpath = EXCLUDED.target_relpath,
                        verification_output = EXCLUDED.verification_output,
                        action_taken = EXCLUDED.action_taken,
                        occurrence_count = EXCLUDED.occurrence_count,
                        updated_at = NOW()
                    """,
                    (
                        record.get("incident_id", ""),
                        record.get("brain_id", "obsidian-brain"),
                        record.get("event_hash", ""),
                        record.get("service_name", ""),
                        record.get("hostname", ""),
                        record.get("level_str", "ERROR"),
                        int(record.get("tier", 4)),
                        record.get("status", "AWAITING_APPROVAL"),
                        record.get("filename", ""),
                        record.get("line_number", ""),
                        record.get("message", ""),
                        record.get("root_cause", ""),
                        record.get("proposed_patch", ""),
                        record.get("target_relpath", ""),
                        record.get("verification_output", ""),
                        record.get("action_taken", ""),
                        int(record.get("occurrence_count", 1)),
                    ),
                )
        return True
    except Exception as e:
        logger.warning(f"SharedPool : Failed upserting fleet_incident ({e}).")
        return False


# -----------------------------------------------------------------------------------------------

def list_fleet_incidents(
    pg_pool: Any,
    logger: Any,
    *,
    brain_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Lists recent triaged fleet incidents ordered by latest update."""
    if not pg_pool:
        return []
    where_clause = "WHERE brain_id = %s " if brain_id else ""
    params = (brain_id, limit) if brain_id else (limit,)
    try:
        with _borrow_conn(pg_pool) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT incident_id, brain_id, event_hash, service_name, hostname, level_str,
                           tier, status, filename, line_number, message, root_cause, proposed_patch,
                           target_relpath, verification_output, action_taken, occurrence_count,
                           created_at, updated_at
                    FROM watchdog_agent.fleet_incidents
                    {where_clause}ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    params,
                )
                rows = cursor.fetchall()
        return [
            {
                "incident_id": r[0],
                "brain_id": r[1],
                "event_hash": r[2],
                "service_name": r[3],
                "hostname": r[4],
                "level_str": r[5],
                "tier": r[6],
                "status": r[7],
                "filename": r[8],
                "line_number": r[9],
                "message": r[10],
                "root_cause": r[11],
                "proposed_patch": r[12],
                "target_relpath": r[13],
                "verification_output": r[14],
                "action_taken": r[15],
                "occurrence_count": r[16],
                "created_at": r[17].isoformat() if r[17] else "",
                "updated_at": r[18].isoformat() if r[18] else "",
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"SharedPool : Failed listing fleet_incidents ({e}).")
        return []

