#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Root-level environment bootstrapper and singleton manager for 08-Squad-Agent.
Sets up system path, redirects virtualenv execution, and instantiates the application 
configuration loader and the UniLog logging engine exactly once.

DATA FLOW:
1. Resolves workspace and virtualenv paths.
2. Directs execution to the virtualenv Python interpreter.
3. Loads production or standalone YAML configuration profile via microservice-toolbox.
4. Spawns the UniLog logger singleton and sets it on the config handle.

KEY PARAMETERS:
- config: Singleton AppConfig instance.
- logger: Singleton UniLog logger instance.
"""

import sys
from os import environ as osEnviron
from pathlib import Path as pathPath

# -----------------------------------------------------------------------------------------------
# 1. Path & Virtual Environment Bootstrapping
# Inject microservice-toolbox path dynamically so we can import bootstrap_microservice
_self_dir = pathPath(__file__).resolve()
_toolbox_env = pathPath(sys.path[0]).parent if "MICROSERVICE_TOOLBOX_PATH" in sys.path else None
_workspace_root = None
for parent in [_self_dir] + list(_self_dir.parents):
    if (parent / "microservice-toolbox").exists():
        _workspace_root = parent
        break
    if (parent / "Bastien-Antigravity" / "microservice-toolbox").exists():
        _workspace_root = parent / "Bastien-Antigravity"
        break
if not _workspace_root:
    for p in [pathPath.cwd()] + list(pathPath.cwd().parents):
        if (p / "microservice-toolbox").exists():
            _workspace_root = p
            break
        if (p / "Bastien-Antigravity" / "microservice-toolbox").exists():
            _workspace_root = p / "Bastien-Antigravity"
            break
if not _workspace_root:
    _workspace_root = _self_dir.parent.parent.parent.parent.parent

_toolbox_path = _workspace_root / "microservice-toolbox" / "python"
if _toolbox_path.exists() and str(_toolbox_path) not in sys.path:
    sys.path.insert(0, str(_toolbox_path))

from microservice_toolbox.utils.bootstrap import bootstrap_microservice
bootstrap_microservice(__file__, app_name="squad_agent")

# -----------------------------------------------------------------------------------------------
# 2. Singleton Instantiation (Config & Logger)
from microservice_toolbox.config.loader import load_config as toolboxLoadConfig
from microservice_toolbox.logger import UniLog as toolboxUniLog

# Scan argv to determine the profile without running a full CLI parser
_profile = None
for i in range(1, len(sys.argv) - 1):
    if sys.argv[i] == "--profile":
        _profile = sys.argv[i + 1]
        break
    elif sys.argv[i] == "-p" and sys.argv[i + 1] in ("standalone", "production", "docker", "local", "staging"):
        _profile = sys.argv[i + 1]
        break

_OFFLINE_CLI_COMMANDS = frozenset({
    "audit_ports",
    "brain_health_audit",
    "validate_compliance",
    "build_inventory",
    "fleet_init_update",
    "hardening_yaml",
    "joint_audit_purger",
    "preflight_check",
    "close_mission",
    "convert_agents",
    "debloat_audit",
    "ensure_frontmatter",
    "eval_agent",
    "mission_help",
    "persona_extractor",
    "check_coherence",
    "map_feats",
    "fix_feats",
    "fleet_version",
    "bump_version",
    "checkpoint",
    "format_compliance",
})

# Determine app_name matching the command name argument
_app_name = "squad_agent"
_cmd_slug = ""
if len(sys.argv) >= 2:
    # First argument is the subcommand when routing through main.py
    cmd_arg = sys.argv[1].replace("-", "_").lower()
    if cmd_arg != "main.py" and not cmd_arg.startswith("_"):
        _cmd_slug = cmd_arg
        _app_name = f"squad_agent_{cmd_arg}"

if not _profile:
    _env_profile = osEnviron.get("CONFIG_PROFILE", "").strip()
    _is_docker = osEnviron.get("DOCKER_ENV") == "true"
    _service_root = _self_dir.parent.parent.parent
    if _cmd_slug in _OFFLINE_CLI_COMMANDS:
        _profile = "standalone"
    elif _env_profile in ("standalone", "production", "staging", "test"):
        _profile = _env_profile
    elif _is_docker and (_service_root / "production.yaml").exists():
        _profile = "production"
    else:
        _profile = "standalone"

# Load configuration exactly once
config = toolboxLoadConfig(_profile, input_args=[])
config_data = config.data

# Setup UniLog exactly once (offline CLI commands default to 'minimal' to avoid socket stalls)
_lvl = "debug" if ("-v" in sys.argv or "--verbose" in sys.argv) else "info"
_config_handle = getattr(config, "_handle", 0) or 0
_explicit_logger_profile = osEnviron.get("APP_LOGGER_PROFILE") or osEnviron.get("LOGGER_PROFILE")
if _explicit_logger_profile:
    _logger_profile = _explicit_logger_profile
elif _cmd_slug in _OFFLINE_CLI_COMMANDS:
    _logger_profile = "minimal"
    osEnviron.setdefault("LOGGER_PROFILE", "minimal")
else:
    _logger_profile = "standard"

logger = toolboxUniLog(
    app_name=_app_name,
    config_profile=_profile,
    logger_profile=_logger_profile,
    log_level=_lvl,
    config_handle=_config_handle
)
config.set_logger(logger)

if config is None:
    raise RuntimeError("08-Squad-Agent bootstrap failed to initialize configuration")
if logger is None:
    raise RuntimeError("08-Squad-Agent bootstrap failed to initialize UniLog logger")


