#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Root-level environment bootstrapper and singleton manager for 08-Base-Scripts.
Sets up system path, redirects virtualenv execution, and instantiates the application 
configuration loader and the UniLog logging engine exactly once.

DATA FLOW:
1. Resolves workspace and virtualenv paths.
2. Directs execution to the virtualenv Python interpreter.
3. Loads standalone YAML configuration profile via microservice-toolbox.
4. Spawns the UniLog logger singleton and sets it on the config handle.
"""

import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# 1. Path & Virtual Environment Bootstrapping
# Inject microservice-toolbox path dynamically so we can import bootstrap_microservice
_self_dir = Path(__file__).resolve()
_workspace_root = None
for parent in [_self_dir] + list(_self_dir.parents):
    if (parent / "microservice-toolbox").exists():
        _workspace_root = parent
        break
if not _workspace_root:
    for p in [Path.cwd()] + list(Path.cwd().parents):
        if (p / "microservice-toolbox").exists():
            _workspace_root = p
            break
if not _workspace_root:
    _workspace_root = _self_dir.parent.parent.parent.parent.parent

_toolbox_path = _workspace_root / "microservice-toolbox" / "python"
if _toolbox_path.exists() and str(_toolbox_path) not in sys.path:
    sys.path.insert(0, str(_toolbox_path))

from microservice_toolbox.utils.bootstrap import bootstrap_microservice
bootstrap_microservice(__file__, app_name="base_scripts")

# -----------------------------------------------------------------------------
# 2. Singleton Instantiation (Config & Logger)
from microservice_toolbox.config.loader import load_config as toolboxLoadConfig

# Scan argv to determine the profile without running a full CLI parser
_profile = "standalone"
for i in range(1, len(sys.argv) - 1):
    if sys.argv[i] in ["--profile", "-p"]:
        _profile = sys.argv[i + 1]
        break

# Load configuration exactly once
config = toolboxLoadConfig(_profile, input_args=[])
config_data = config.data

# Setup UniLog exactly once
_lvl = "debug" if ("-v" in sys.argv or "--verbose" in sys.argv) else "info"
_config_handle = getattr(config, "_handle", 0) or 0

# Determine app_name matching the command name argument
_app_name = "base_scripts"
if len(sys.argv) >= 2:
    # First argument is the subcommand when routing through main.py
    cmd_arg = sys.argv[1].replace("-", "_").lower()
    if cmd_arg != "main.py":
        _app_name = f"base_scripts_{cmd_arg}"

from microservice_toolbox.logger import UniLog
logger = UniLog(
    app_name=_app_name, 
    config_profile="standalone", 
    logger_profile="devel",
    log_level=_lvl,
    config_handle=_config_handle
)
config.set_logger(logger)

# 3. Lazy Database Schema and Tables Initialization
try:
    from lib.pg_pool import get_pg_pool, resolve_schema_name
    _pg_pool = get_pg_pool(config=config, logger=logger)
    if _pg_pool:
        _schema_name = resolve_schema_name(__file__)
        from lib.memory import PostgresMemoryStore
        # Instantiation automatically invokes _init_db() to build schema and tables on-demand
        PostgresMemoryStore(config=config, logger=logger, pg_pool=_pg_pool, schema=_schema_name)
except Exception as _db_err:
    logger.warning("Database lazy-initialisation skipped: {0}".format(_db_err))

