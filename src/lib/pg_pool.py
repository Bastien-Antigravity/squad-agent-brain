#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS: pg_pool
  Shared PostgreSQL connection pool manager for 08-Base-Scripts.
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
from pathlib import Path
from typing import Optional, Any

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

    # Retrieve database configurations
    timescale_db = config.data.get("capabilities", {}).get("timescale_db", {})
    if not timescale_db:
        logger.warning("SharedPool : timescale_db capability missing in configuration.")
        return None

    host = timescale_db.get("ip", "127.0.0.1")
    port = int(timescale_db.get("port", 5432))
    user = timescale_db.get("user", "dbuser")
    password = timescale_db.get("password", "dbuser")
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
    target_repos = ["08-Base-Scripts", "01-Strategic-Nexus", "09-RAG-Engine", "watchdog-agent"]
    for parent in [path] + list(path.parents):
        if parent.name in target_repos:
            return parent.name
    return path.parent.name

