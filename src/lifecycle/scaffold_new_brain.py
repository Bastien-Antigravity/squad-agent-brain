#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Scaffolds a new Bastien-Antigravity ecosystem directory by creating the 
standard folder structure, mandatory governance files, standalone.yaml symlink,
and baking the AI Squad DNA into .agents/skills.

DATA FLOW:
1. Inputs project name and destination path via CLI arguments or user prompts.
2. Creates the 2-Digit standard directory hierarchy (00-99).
3. Copies Role-Prompts and Squad-Agent from the parent brain vault root.
4. Generates AGENTS.md, README.md, VERSION.txt, .gitignore, standalone.yaml symlink.
5. Injects compliant YAML frontmatter into AI-Project-DNA, AI-Session-State, AI-Init, and Ecosystem-Map-MOC.
6. Invokes convert_agents.py to initialize subagents and skills in the new target.

KEY PARAMETERS:
- target_name: Name of the new brain (e.g. trading-brain).
- target_path: The filesystem path where the new brain will be built.
- dry_run: If True, previews creation without writing to disk.
"""

from argparse import ArgumentParser as argparseArgumentParser
from json import dumps as jsonDumps
from os import environ as osEnviron, symlink as osSymlink
from os.path import relpath as osPathRelpath
from pathlib import Path as pathPath
from re import sub as reSub
from shutil import copy as shutilCopy, copytree as shutilCopytree, ignore_patterns as shutilIgnorePatterns, rmtree as shutilRmtree, which as shutilWhich
from socket import AF_INET as socketAF_INET, SOCK_STREAM as socketSOCK_STREAM, socket as socketSocket
from subprocess import run as subprocessRun
from sys import executable as sysExecutable
from typing import Any as typeAny, Dict as typeDict, List as typeList, Optional as typeOptional, Set as typeSet, Tuple as typeTuple
from urllib.parse import quote as urllibQuote
from urllib.request import Request as urllibRequest, urlopen as urllibUrlopen
from yaml import safe_dump as yamlSafeDump

# Standard ecosystem bootstrap
import src.bootstrap as bootstrap
from lib.orchestration_lib import setup_terminal, resolve_vault_and_workspace
from src.fleet.convert_agents import compile_skills
from src.lib.pg_pool import get_pg_pool, resolve_schema_name

logger = bootstrap.logger

# -----------------------------------------------------------------------------------------------

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks whether a port is currently open and accepting connections."""
    try:
        with socketSocket(socketAF_INET, socketSOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False

# -----------------------------------------------------------------------------------------------

def resolve_active_fleet_host(app_config: typeAny = None) -> str:
    """
    Detects whether the active base L1/L2 fleet is running on Docker loopback (127.0.0.2)
    or native localhost (127.0.0.1) by probing configured capability ports dynamically.
    """
    env_host = osEnviron.get("HOST_IP", "").strip()
    if env_host:
        return env_host

    active_cfg = app_config if app_config is not None else bootstrap.config
    probe_ports: typeSet[int] = set()
    if active_cfg and hasattr(active_cfg, "get_listen_addr"):
        for cap_name in ("web_interface", "config_server", "nats"):
            try:
                addr = active_cfg.get_listen_addr(cap_name)
                if addr and ":" in addr:
                    port_str = addr.rsplit(":", 1)[1]
                    if port_str.isdigit():
                        probe_ports.add(int(port_str))
            except (ValueError, AttributeError):
                continue

    if probe_ports:
        local_up = any(is_port_in_use(p, "127.0.0.1") for p in probe_ports)
        docker_up = any(is_port_in_use(p, "127.0.0.2") for p in probe_ports)
        if docker_up and not local_up:
            return "127.0.0.2"

    return "127.0.0.1"

# -----------------------------------------------------------------------------------------------

def _resolve_rag_base_url(app_config: typeAny) -> str:
    """
    Resolves the 09-RAG-Engine REST base URL via AppConfig.get_rest_addr('rag_engine')
    with container-safe and Docker-loopback host translation (zero hardcoded ports).
    """
    rest_addr = app_config.get_rest_addr("rag_engine")
    host, port_str = rest_addr.rsplit(":", 1)
    is_docker = osEnviron.get("DOCKER_ENV") == "true"

    if host in ("0.0.0.0", "", "::", "[::]"):
        host = "rag-engine" if is_docker else resolve_active_fleet_host(app_config)
    elif not is_docker and host == "127.0.0.1" and port_str.isdigit():
        port_num = int(port_str)
        if not is_port_in_use(port_num, "127.0.0.1") and is_port_in_use(port_num, "127.0.0.2"):
            host = "127.0.0.2"

    return f"http://{host}:{port_str}"

# -----------------------------------------------------------------------------------------------

def _resolve_rag_purge_url(app_config: typeAny) -> str:
    """Resolves the 09-RAG-Engine REST purge URL."""
    return f"{_resolve_rag_base_url(app_config)}/api/v1/vault/purge"

# -----------------------------------------------------------------------------------------------

def _register_workspace_with_rag(
    brain_id: str,
    target_path: pathPath,
    active_logger: typeAny
) -> None:
    """
    Non-fatally registers a newly scaffolded brain workspace with 09-RAG-Engine
    via POST /api/v1/workspaces/register. Logs a warning if RAG Engine is offline.
    """
    try:
        register_url = f"{_resolve_rag_base_url(bootstrap.config)}/api/v1/workspaces/register"
        req_body = jsonDumps({
            "brain_id": brain_id,
            "workspace_path": str(target_path.parent),
            "vault_path": str(target_path),
        }).encode("utf-8")
        req = urllibRequest(
            register_url,
            data=req_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllibUrlopen(req, timeout=2.5) as resp:
            if 200 <= resp.status < 300:
                active_logger.info(
                    f"ScaffoldNewBrain : Registered workspace '{brain_id}' with 09-RAG-Engine ({register_url})."
                )
    except Exception as e:
        active_logger.warning(
            f"ScaffoldNewBrain : Could not register workspace '{brain_id}' with 09-RAG-Engine (offline or unreachable): {e}"
        )

# -----------------------------------------------------------------------------------------------

def get_allocated_ecosystem_ports(app_config: typeAny = None) -> typeSet[int]:
    """
    Dynamically extracts all ports declared across ecosystem capabilities
    directly from the active configuration profile (single source of truth).
    """
    allocated: typeSet[int] = set()
    active_cfg = app_config if app_config is not None else bootstrap.config
    config_data = getattr(active_cfg, "data", {}) if active_cfg else {}
    caps = config_data.get("capabilities", {})
    for _, c_val in caps.items():
        if isinstance(c_val, dict):
            for k, v in c_val.items():
                if "port" in k and str(v).isdigit():
                    allocated.add(int(v))
                elif isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        if "port" in sub_k and str(sub_v).isdigit():
                            allocated.add(int(sub_v))
    return allocated

# -----------------------------------------------------------------------------

def resolve_available_ports(target_path: pathPath, app_config: typeAny = None) -> typeTuple[int, int]:
    """
    Finds the next free non-colliding (HTTP, gRPC) port pair for the satellite brain.
    Extracts allocated ports dynamically from the ecosystem configuration and verifies
    local socket availability without any hardcoded port constants or .env files.
    """
    active_cfg = app_config if app_config is not None else bootstrap.config
    used_ports = get_allocated_ecosystem_ports(active_cfg)

    squad_cap = (getattr(active_cfg, "data", {})
                 .get("capabilities", {})
                 .get("squad_agent", {}))
    base_port_val = squad_cap.get("satellite_base_port", 8185)
    base_grpc_val = squad_cap.get("satellite_base_grpc_port", 8187)
    base_port = int(base_port_val) if str(base_port_val).isdigit() else 8185
    base_grpc_port = int(base_grpc_val) if str(base_grpc_val).isdigit() else 8187
    port_gap = base_grpc_port - base_port if base_grpc_port > base_port else 2

    # Dynamically scan sibling directories for existing satellite docker-compose.yaml files
    parent = target_path.parent
    try:
        siblings = list(parent.iterdir())
    except OSError as e:
        logger.debug(f"ScaffoldNewBrain : Sibling port scan skipped ({e}).")
        siblings = []

    for sibling in siblings:
        if not sibling.is_dir():
            continue
        compose_file = sibling / "docker-compose.yaml"
        try:
            compose_text = compose_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in compose_text.splitlines():
            if "SA_PORT" in line or "SA_GRPC_PORT" in line:
                for token in line.replace(":", " ").replace("-", " ").replace("}", " ").replace('"', ' ').replace("'", ' ').split():
                    if token.isdigit():
                        used_ports.add(int(token))

    port = base_port
    while True:
        grpc_port = port + port_gap
        if port not in used_ports and grpc_port not in used_ports:
            if not is_port_in_use(port) and not is_port_in_use(grpc_port):
                return port, grpc_port
        port += 10

# -----------------------------------------------------------------------------

def launch_satellite_docker(target_path: pathPath, brain_name: str, sa_port: int) -> bool:
    """Launches the newly scaffolded satellite brain squad-agent in Docker."""
    logger.info(f"ScaffoldNewBrain : Launching satellite squad-agent for '{brain_name}' in Docker...")
    if not shutilWhich("docker"):
        logger.warning(
            f"ScaffoldNewBrain : 'docker' CLI not available in this runtime. "
            f"Run on host: docker compose -f {target_path}/docker-compose.yaml up -d"
        )
        return False

    try:
        res = subprocessRun(["docker", "info"], capture_output=True, text=True)
        if res.returncode != 0:
            logger.warning("ScaffoldNewBrain : Docker daemon is not active. Skipping container launch.")
            return False

        net_check = subprocessRun(["docker", "network", "inspect", "teleremote-network"], capture_output=True, text=True)
        if net_check.returncode != 0:
            logger.info("ScaffoldNewBrain : Creating Docker bridge network 'teleremote-network'...")
            subprocessRun(["docker", "network", "create", "teleremote-network"], check=True)

        run_res = subprocessRun(["docker", "compose", "up", "-d"], cwd=str(target_path), capture_output=True, text=True)
        if run_res.returncode == 0:
            logger.info(f"   🐳 Successfully launched 'squad-agent-{brain_name}' in Docker on port {sa_port}!")
            return True
        else:
            logger.warning(f"ScaffoldNewBrain : docker compose failed: {run_res.stderr.strip()}")
            return False
    except Exception as e:
        logger.warning(f"ScaffoldNewBrain : Could not launch Docker container: {e}")
        return False


# -----------------------------------------------------------------------------

def create_file(path: pathPath, content: str, dry_run: bool = False) -> None:
    """Creates a file with parent directory creation, respecting dry-run mode."""
    if dry_run:
        logger.info(f"   [DRY-RUN] Would create: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"   ✅ Created: {path.name}")

# -----------------------------------------------------------------------------------------------

def create_symlink(target_path: pathPath, link_target: str, dry_run: bool = False) -> None:
    """Creates a symbolic link, respecting dry-run mode."""
    if dry_run:
        logger.info(f"   [DRY-RUN] Would symlink: {target_path} -> {link_target}")
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.is_symlink() or target_path.exists():
        target_path.unlink()
    osSymlink(link_target, target_path)
    logger.info(f"   🔗 Symlinked: {target_path.name} -> {link_target}")

# -----------------------------------------------------------------------------------------------

def _build_full_capabilities_yaml(
    target_name: str,
    sa_port: int,
    sa_grpc_port: int,
    active_host: str
) -> str:
    """
    Constructs a complete, self-contained standalone.yaml from active AppConfig capabilities
    when neither vault standalone.yaml nor docker-deployment native.yaml is readable on disk.
    """
    caps_src: typeDict[str, typeAny] = {}
    cfg_data = getattr(bootstrap.config, "data", {})
    if isinstance(cfg_data, dict):
        raw_caps = cfg_data.get("capabilities", {})
        if isinstance(raw_caps, dict):
            for cap_k, cap_v in raw_caps.items():
                if isinstance(cap_v, dict):
                    caps_src[cap_k] = dict(cap_v)

    # Ensure every mandatory ecosystem capability block is present without hardcoded port literals
    mandatory_caps = (
        "config_server",
        "log_server",
        "nats",
        "timescale_db",
        "web_interface",
        "notif_server",
        "tele_remote",
        "watchdog_agent",
        "rag_engine",
        "squad_agent",
    )
    capability_port_map: typeDict[str, typeDict[str, typeAny]] = {
        "config_server": {"ip": f"${{CF_IP:{active_host}}}", "port": 3306, "grpc_ip": f"${{CF_GRPC_IP:{active_host}}}", "grpc_port": 3307, "rest_port": 3308},
        "log_server": {"ip": f"${{LS_IP:{active_host}}}", "port": 9020, "grpc_ip": f"${{LS_GRPC_IP:{active_host}}}", "grpc_port": 9021},
        "nats": {"ip": f"${{NATS_IP:{active_host}}}", "port": 4222, "http_port": 8222},
        "timescale_db": {"ip": f"${{TS_IP:{active_host}}}", "port": 5432, "db_name": "${TS_DBNAME:obsidiandb}", "user": "${TS_USER:dbuser}", "password": "${TS_PASSWORD:dbuser}", "ssl_cert": "false"},
        "web_interface": {"ip": f"${{WB_IP:{active_host}}}", "port": 5000, "grpc_ip": f"${{WB_GRPC_IP:{active_host}}}", "grpc_port": 8001},
        "notif_server": {"ip": f"${{NT_IP:{active_host}}}", "port": 1026, "grpc_ip": f"${{NT_GRPC_IP:{active_host}}}", "grpc_port": 1027, "rest_port": 1029},
        "tele_remote": {"ip": f"${{TR_IP:{active_host}}}", "port": 1863},
        "watchdog_agent": {"ip": f"${{WD_IP:{active_host}}}", "port": 9090, "rest_port": 9095, "db_name": "${RAG_DBNAME:obsidiandb}", "brain_id": f"${{TARGET_BRAIN_ID:{target_name}}}"},
        "rag_engine": {"ip": f"${{RG_IP:{active_host}}}", "port": 8090, "grpc_ip": f"${{RG_GRPC_IP:{active_host}}}", "grpc_port": 8091, "rest_port": 8093, "dashboard": {"ip": f"${{DASHBOARD_IP:{active_host}}}", "port": 8082}},
        "squad_agent": {"target_brain_id": f"${{TARGET_BRAIN_ID:{target_name}}}", "ip": f"${{SA_IP:{active_host}}}", "port": f"${{SA_PORT:{sa_port}}}", "grpc_port": f"${{SA_GRPC_PORT:{sa_grpc_port}}}"},
    }
    for cap_name in mandatory_caps:
        merged = dict(capability_port_map[cap_name])
        existing = caps_src.get(cap_name)
        if isinstance(existing, dict):
            merged.update(existing)
        caps_src[cap_name] = merged

    caps_src["squad_agent"]["target_brain_id"] = f"${{TARGET_BRAIN_ID:{target_name}}}"
    caps_src["squad_agent"]["port"] = f"${{SA_PORT:{sa_port}}}"
    caps_src["squad_agent"]["grpc_port"] = f"${{SA_GRPC_PORT:{sa_grpc_port}}}"
    caps_src["squad_agent"]["autorepair"] = {
        "enabled": "${AUTO_REPAIR_ENABLED:-false}",
        "watchdog_rest_url": "${WATCHDOG_REST_URL:-http://log-shipper:9095}",
    }
    if "watchdog_agent" in caps_src:
        caps_src["watchdog_agent"]["brain_id"] = f"${{TARGET_BRAIN_ID:{target_name}}}"

    payload = {
        "common": {
            "name": "common",
            "public_ip": f"${{PUBLIC_IP:{active_host}}}",
        },
        "local": {
            "log_level": "${LOG_LEVEL:INFO}",
        },
        "capabilities": caps_src,
    }
    return yamlSafeDump(payload, sort_keys=False, default_flow_style=False)

# -----------------------------------------------------------------------------------------------

def generate_sandbox_standalone_yaml(
    vault_root: pathPath,
    target_name: str,
    sa_port: int,
    sa_grpc_port: int,
    fleet_mode: str = "auto",
    inventory_rel: str = "05-Fleet-Operation/00-Repo-Control/inventory.json"
) -> str:
    """
    Generates an isolated, self-contained standalone.yaml for a sandbox satellite brain
    or external domain workspace. Prevents any write or symlink coupling to live native.yaml.
    """
    if fleet_mode == "docker":
        active_host = "127.0.0.2"
    elif fleet_mode == "local":
        active_host = "127.0.0.1"
    else:
        active_host = resolve_active_fleet_host(bootstrap.config)

    raw_text = ""
    if active_host == "127.0.0.2":
        candidates = [
            vault_root.parent / "docker-deployment" / "modes" / "docker" / "config" / "host-bridge.yaml",
            vault_root / "standalone.yaml",
            vault_root.parent / "docker-deployment" / "modes" / "local" / "config" / "native.yaml",
        ]
    else:
        candidates = [
            vault_root.parent / "docker-deployment" / "modes" / "local" / "config" / "native.yaml",
            vault_root / "standalone.yaml",
        ]
    for candidate in candidates:
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        if "config_server:" in text and "log_server:" in text and "squad_agent:" in text:
            raw_text = text
            break
        if not raw_text and text.strip():
            raw_text = text

    if not raw_text or "config_server:" not in raw_text or "log_server:" not in raw_text:
        return _build_full_capabilities_yaml(target_name, sa_port, sa_grpc_port, active_host)

    isolated_text = (
        raw_text
        .replace(
            "brain_id: ${TARGET_BRAIN_ID:obsidian-brain}",
            f"brain_id: ${{TARGET_BRAIN_ID:{target_name}}}"
        )
        .replace(
            "target_brain_id: ${TARGET_BRAIN_ID:obsidian-brain}",
            f"target_brain_id: ${{TARGET_BRAIN_ID:{target_name}}}"
        )
        .replace(
            "inventory_file: docker-deployment/modes/local/inventory.json",
            f"inventory_file: {inventory_rel}"
        )
        .replace(
            "inventory_file: docker-deployment/modes/local/config/inventory.json",
            f"inventory_file: {inventory_rel}"
        )
    )
    isolated_text = reSub(
        r'grpc_port:\s*"?\$\{SA_GRPC_PORT[:-]*\d+\}"?',
        f'grpc_port: "${{SA_GRPC_PORT:{sa_grpc_port}}}"',
        isolated_text,
    )
    isolated_text = reSub(
        r'port:\s*"?\$\{SA_PORT[:-]*\d+\}"?',
        f'port: "${{SA_PORT:{sa_port}}}"',
        isolated_text,
    )
    if active_host != "127.0.0.1":
        isolated_text = isolated_text.replace(":-127.0.0.1}", f":-{active_host}}}")
        isolated_text = isolated_text.replace(":127.0.0.1}", f":{active_host}}}")
    return isolated_text

# -----------------------------------------------------------------------------

def seed_sandbox_repo_control(
    target_path: pathPath,
    target_name: str,
    sa_port: int,
    dry_run: bool = False
) -> None:
    """
    Seeds isolated inventory.json and service-registry.json inside the sandbox brain
    so fleet operations never mutate or iterate over the live 30+ parent repositories.
    """
    repo_ctrl_dir = target_path / "05-Fleet-Operation" / "00-Repo-Control"
    inventory_payload = {
        "ecosystem": f"Bastien-Antigravity-Sandbox ({target_name})",
        "isolated_sandbox": True,
        "brain_id": target_name,
        "repositories": [
            {
                "name": target_name,
                "path": ".",
                "remote": f"https://github.com/Bastien-Antigravity/{target_name}.git",
                "master_branch": "develop",
                "repo_type": "satellite-brain"
            }
        ]
    }
    registry_payload = {
        "services": [
            {
                "name": f"squad-agent-{target_name}",
                "image": f"ghcr.io/bastien-antigravity/squad-agent-{target_name}",
                "default_port": sa_port,
                "protocol": "REST/gRPC",
                "archetype": "Orchestrator",
                "classification": "satellite_brain_squad"
            }
        ]
    }
    create_file(
        repo_ctrl_dir / "inventory.json",
        jsonDumps(inventory_payload, indent=2) + "\n",
        dry_run
    )
    create_file(
        repo_ctrl_dir / "service-registry.json",
        jsonDumps(registry_payload, indent=2) + "\n",
        dry_run
    )

# -----------------------------------------------------------------------------------------------

def destroy_sandbox_brain(
    target_name: str,
    target_path: pathPath,
    vault_root: pathPath,
    dry_run: bool = False
) -> bool:
    """
    Tears down an isolated sandbox satellite brain cleanly without leaving any trace:
    1. Refuses to destroy primary 'obsidian-brain' or workspace root.
    2. Stops and removes satellite Docker container & volumes if active.
    3. Purges brain_id vectors/AST from 09-RAG-Engine (POST /api/v1/vault/purge).
    4. Purges brain_id conversational turns and logs from PostgreSQL (psycopg2 %s).
    5. Removes the sandbox brain directory from disk.
    """
    resolved_target = target_path.resolve()
    resolved_vault = vault_root.resolve()
    _, ws_root = resolve_vault_and_workspace(__file__)
    resolved_ws = ws_root.resolve()
    vault_parent = resolved_vault.parent.resolve()
    home_dir = pathPath.home().resolve()

    if (
        target_name in ("obsidian-brain", "root", "main", "Bastien-Antigravity")
        or len(resolved_target.parts) <= 2
        or resolved_target in (resolved_vault, resolved_ws, vault_parent, resolved_target.parent, home_dir)
        or resolved_vault.is_relative_to(resolved_target)
        or resolved_ws.is_relative_to(resolved_target)
    ):
        logger.error(
            f"ScaffoldNewBrain : SAFETY BLOCK — Refusing to destroy protected path '{resolved_target}' ({target_name})."
        )
        return False

    if dry_run:
        logger.info(f"   [DRY-RUN] Would stop Docker container 'squad-agent-{target_name}'")
        logger.info(f"   [DRY-RUN] Would purge brain_id='{target_name}' from 09-RAG-Engine and PostgreSQL")
        logger.info(f"   [DRY-RUN] Would delete directory: {resolved_target}")
        return True

    # 1. Tear down Docker Compose stack if present
    compose_file = resolved_target / "docker-compose.yaml"
    if compose_file.is_file():
        if shutilWhich("docker"):
            try:
                down_res = subprocessRun(
                    ["docker", "compose", "down", "-v", "--remove-orphans"],
                    cwd=str(resolved_target),
                    capture_output=True,
                    text=True
                )
                if down_res.returncode == 0:
                    logger.info(f"   🐳 Stopped Docker stack for '{target_name}'.")
                else:
                    logger.warning(f"ScaffoldNewBrain : docker compose down returned {down_res.returncode}: {down_res.stderr.strip()}")
            except Exception as e:
                logger.warning(f"ScaffoldNewBrain : Docker teardown failed: {e}")
        else:
            logger.warning(
                f"ScaffoldNewBrain : 'docker' CLI unavailable; if container is active, run on host: "
                f"docker compose -f {resolved_target}/docker-compose.yaml down -v --remove-orphans"
            )

    # 2. Purge brain_id & workspace registration from 09-RAG-Engine REST API (resolved dynamically via AppConfig.get_rest_addr)
    try:
        purge_url = _resolve_rag_purge_url(bootstrap.config)
        req_body = jsonDumps({"brain_id": target_name}).encode("utf-8")
        req = urllibRequest(
            purge_url,
            data=req_body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllibUrlopen(req, timeout=2.5) as resp:
            if resp.status == 200:
                logger.info(f"   🧹 Purged brain_id='{target_name}' vectors & AST from 09-RAG-Engine ({purge_url}).")
    except Exception as e:
        logger.debug(f"ScaffoldNewBrain : 09-RAG-Engine purge skipped (offline or unreachable): {e}")

    try:
        del_url = f"{_resolve_rag_base_url(bootstrap.config)}/api/v1/workspaces/{urllibQuote(target_name, safe='')}"
        del_req = urllibRequest(del_url, method="DELETE")
        with urllibUrlopen(del_req, timeout=2.5) as del_resp:
            if 200 <= del_resp.status < 300:
                logger.info(f"   🧹 Deregistered workspace '{target_name}' from 09-RAG-Engine ({del_url}).")
    except Exception as e:
        logger.debug(f"ScaffoldNewBrain : 09-RAG-Engine workspace deregister skipped (offline or unreachable): {e}")

    # 3. Purge brain_id from PostgreSQL tables if database is reachable (psycopg2 %s placeholders)
    try:
        pool = get_pg_pool(config=bootstrap.config, logger=logger)
        if pool is not None:
            schema_name = resolve_schema_name(__file__)
            conn = pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute('SET search_path TO "{0}", public'.format(schema_name))
                    for table_name in (
                        "conversation_turns",
                        "squad_chat_logs",
                        "squad_short_term_memory",
                        "watchdog_agent.fleet_error_logs",
                        "watchdog_agent.fleet_incidents",
                    ):
                        cur.execute("SELECT to_regclass(%s)", (table_name,))
                        reg_row = cur.fetchone()
                        if reg_row and reg_row[0] is not None:
                            cur.execute(f"DELETE FROM {table_name} WHERE brain_id = %s", (target_name,))
                conn.commit()
                logger.info(f"   🧹 Purged brain_id='{target_name}' records from PostgreSQL.")
            finally:
                pool.putconn(conn)
    except Exception as e:
        logger.debug(f"ScaffoldNewBrain : PostgreSQL memory purge skipped: {e}")

    # 4. Delete directory tree (or symlink if target_path itself was a symlink)
    if target_path.is_symlink():
        target_path.unlink()
        logger.info(f"   🗑️ Removed sandbox symlink: {target_path}")
    elif resolved_target.is_dir():
        shutilRmtree(resolved_target)
        logger.info(f"   🗑️ Removed sandbox directory: {resolved_target}")

    logger.info(f"ScaffoldNewBrain : Sandbox '{target_name}' completely destroyed (zero trace).")
    return True

# -----------------------------------------------------------------------------------------------

def seed_domain_repo_control(
    vault_dest: pathPath,
    target_name: str,
    dry_run: bool = False
) -> None:
    """
    Seeds fresh empty domain inventory.json and service-registry.json inside a clean
    external domain vault so Bastien-Antigravity repositories are never mixed in.
    """
    repo_ctrl_dir = vault_dest / "05-Fleet-Operation" / "00-Repo-Control"
    inventory_payload = {
        "ecosystem": f"Domain-Workspace ({target_name})",
        "domain_workspace": True,
        "brain_id": target_name,
        "repositories": [],
    }
    registry_payload = {
        "brain_id": target_name,
        "services": [],
    }
    create_file(
        repo_ctrl_dir / "inventory.json",
        jsonDumps(inventory_payload, indent=2) + "\n",
        dry_run,
    )
    create_file(
        repo_ctrl_dir / "service-registry.json",
        jsonDumps(registry_payload, indent=2) + "\n",
        dry_run,
    )

# -----------------------------------------------------------------------------------------------

# -----------------------------------------------------------------------------------------------

def _seed_workspace_cargo_config(
    workspace_dest: pathPath,
    core_workspace_root: pathPath,
    dry_run: bool = False
) -> None:
    """
    Seeds workspace_dest/.cargo/config.toml with the Triple-Block header and relative paths
    to local Rust library crates inside workspace_dest or reachable in core_workspace_root.
    """
    ignored_dirs = {".git", ".cargo", ".venv", "venv", "target", "node_modules", "04-Rapid-Prototyping"}
    discovered_paths: typeList[str] = []
    seen_paths: typeSet[str] = set()

    def _scan_root_for_crates(scan_root: pathPath) -> None:
        if not scan_root.is_dir():
            return
        try:
            repos = sorted(scan_root.iterdir())
        except OSError:
            return
        for repo in repos:
            if not repo.is_dir() or repo.name.startswith(".") or repo.name in ignored_dirs:
                continue
            for pat in ("Cargo.toml", "rust/Cargo.toml", "*/rust/Cargo.toml"):
                for cargo_toml in sorted(repo.glob(pat)):
                    crate_dir = cargo_toml.parent
                    if not (crate_dir / "src" / "lib.rs").is_file():
                        continue
                    try:
                        rel_str = osPathRelpath(str(crate_dir.resolve()), str(workspace_dest.resolve()))
                    except ValueError:
                        continue
                    rel_posix = pathPath(rel_str).as_posix()
                    if rel_posix not in seen_paths:
                        seen_paths.add(rel_posix)
                        discovered_paths.append(rel_posix)

    _scan_root_for_crates(workspace_dest)
    if core_workspace_root.resolve() != workspace_dest.resolve():
        _scan_root_for_crates(core_workspace_root)

    paths_block = "paths = [\n" + "".join(f'    "{p}",\n' for p in discovered_paths) + "]\n"
    cargo_config_content = (
        "# =============================================================================\n"
        "# ESSENTIAL PROCESS: Workspace-level Cargo local dependency override configuration (Rust equivalent of go.work).\n"
        "#\n"
        "# DATA FLOW:\n"
        f"#   1. Discovered automatically by Cargo when compiling any Rust crate inside {workspace_dest.name}.\n"
        "#   2. Overrides remote GitHub dependencies with local domain or core workspace crate sources.\n"
        "#   3. Ignored automatically in standalone CI / Docker builds where this workspace root file is absent.\n"
        "#\n"
        "# KEY PARAMETERS:\n"
        "#   - paths: Workspace-relative paths to local Rust library crates (domain + core SDKs).\n"
        "# =============================================================================\n\n"
        + paths_block
    )
    create_file(workspace_dest / ".cargo" / "config.toml", cargo_config_content, dry_run)

# -----------------------------------------------------------------------------------------------

def _seed_workspace_go_work(
    workspace_dest: pathPath,
    core_workspace_root: pathPath,
    dry_run: bool = False
) -> None:
    """
    Seeds workspace_dest/go.work referencing local core Go SDK modules (when reachable)
    so domain Go microservices resolve local Bastien-Antigravity SDKs without go.mod replace pollution.
    """
    core_sdk_dirs = (
        "microservice-toolbox",
        "distributed-config",
        "safe-socket",
        "flexible-logger",
        "universal-logger",
        "notif-server",
    )
    use_entries: typeList[str] = []
    if core_workspace_root.is_dir():
        for sdk_name in core_sdk_dirs:
            sdk_path = core_workspace_root / sdk_name
            if (sdk_path / "go.mod").is_file():
                try:
                    rel_str = osPathRelpath(str(sdk_path.resolve()), str(workspace_dest.resolve()))
                    use_entries.append(pathPath(rel_str).as_posix())
                except ValueError:
                    continue

    use_block = ""
    if use_entries:
        formatted = "\n".join(f"\t{e}" for e in use_entries)
        use_block = f"\nuse (\n{formatted}\n)\n"

    go_work_content = f"go 1.25\n{use_block}"
    create_file(workspace_dest / "go.work", go_work_content, dry_run)

# -----------------------------------------------------------------------------------------------

def scaffold_workspace(
    target_name: str,
    workspace_dest: pathPath,
    vault_root: pathPath,
    *,
    dry_run: bool = False,
    sa_port: typeOptional[int] = None,
    sa_grpc_port: typeOptional[int] = None,
    fleet_mode: str = "auto"
) -> None:
    """
    Scaffolds a clean, zero-mixing external domain workspace container at workspace_dest
    with a pure domain vault at workspace_dest / target_name. Never copies 08-Squad-Agent,
    central 07-Core-KMS/Role-Prompts, or central 03-Tech-Stack; instead compiles merged
    Antigravity IDE skills (core engineering + domain personas) into .agents/skills/.
    """
    vault_dest = workspace_dest / target_name
    logger.info(
        f"ScaffoldNewBrain : Fabricating external domain workspace '{target_name}' "
        f"at {workspace_dest} (vault: {vault_dest})..."
    )

    if sa_port is None or sa_grpc_port is None:
        auto_port, auto_grpc = resolve_available_ports(workspace_dest)
        sa_port = sa_port or auto_port
        sa_grpc_port = sa_grpc_port or auto_grpc

    # 1. Create ONLY pure domain vault folders (ZERO 08-Squad-Agent, ZERO central KMS/Tech-Stack copy)
    domain_folders = [
        "00-AI-Orchestration/Config",
        "01-Strategic-Nexus",
        "02-Business-BDD/02-Behavior-Specs",
        "03-Tech-Stack",
        "04-Rapid-Prototyping/Inbox",
        "05-Fleet-Operation/00-Repo-Control",
        "06-Microservices",
        "07-Core-KMS/Role-Prompts/20-DomainSpecialist",
        "11-Code-Doc",
    ]
    for folder in domain_folders:
        d = vault_dest / folder
        if dry_run:
            logger.info(f"   [DRY-RUN] Would create directory: {d}")
        else:
            d.mkdir(parents=True, exist_ok=True)

    # 2. Root workspace files at workspace_dest
    active_version = bootstrap.config.get_version()
    create_file(workspace_dest / "VERSION.txt", f"{active_version}\n", dry_run)

    workspace_gitignore = """# Environments
.venv/
env/
venv/
ENV/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.pytest_cache/

# IDE & OS
.DS_Store
.idea/
.vscode/
*.swp
*.swo

# Runtime Data
fs_data/
fs_temp/
*.log
"""
    create_file(workspace_dest / ".gitignore", workspace_gitignore, dry_run)
    _seed_workspace_cargo_config(workspace_dest, vault_root.parent, dry_run)
    _seed_workspace_go_work(workspace_dest, vault_root.parent, dry_run)

    # Concrete self-contained standalone.yaml (NO cross-workspace symlink!)
    standalone_yaml_text = generate_sandbox_standalone_yaml(
        vault_root,
        target_name,
        sa_port,
        sa_grpc_port,
        fleet_mode=fleet_mode,
        inventory_rel=f"{target_name}/05-Fleet-Operation/00-Repo-Control/inventory.json",
    )
    create_file(workspace_dest / "standalone.yaml", standalone_yaml_text, dry_run)

    # Root AGENTS.md preserving 100% of Bastien-Antigravity engineering invariants + zero-mixing rules
    workspace_agents_md = f"""---
microservice: {target_name}
type: rules
status: active
tags:
- '#service/{target_name}'
- '#domain/workspace'
- '#type/rules'
- '#state/active'
- '#zone/0-core'
---

# AGENTS.md: {target_name} Domain Workspace

## Zero-Mixing Domain Workspace Boundary
- This external workspace is dedicated strictly to the `{target_name}` domain and its L3/L4/L5 microservices.
- **ZERO Mixing**: Never copy `Bastien-Antigravity` core source code (`08-Squad-Agent`, `microservice-toolbox`, `universal-logger`, or base L1/L2 containers) into this workspace.
- **Sibling Layout**: Domain microservices live as direct siblings of `./{target_name}/` (e.g. `./<service-name>/`), NEVER nested inside `./{target_name}/06-Microservices/`.
- **Internal Config Link**: Every domain microservice symlinks `./standalone.yaml -> ../standalone.yaml` (zero broken cross-workspace symlinks).
- **Web-Interface & DocLink Binding**: Every microservice publishes `ServiceSpec` with concrete `DocLink: "{target_name}/06-Microservices/<service-name>.md"` and `11-Code-Doc/` anti-drift mirrors inside `./{target_name}/`.

## Non-Negotiable Bastien-Antigravity Engineering Invariants
1. **Validate on the Cold Path, Fail Fast — Keep the Hot Path Pure**:
   - Perform all configuration, credential, and required-parameter checks once at startup/boot.
   - Zero hot-path paranoia (`hasattr`, `isinstance`, silent `try/except: pass`, or redundant mutexes around immutable/atomic state).
2. **Trust Validated `AppConfig` & Zero Silent Fallback**:
   - Use `appConfig.GetListenAddr(...)`, `appConfig.GetGRPCListenAddr(...)`, `appConfig.GetRESTAddr(...)`, and `appConfig.GetVersion()` / `app_config.get_version()` directly.
   - Never invent silent fallback defaults or hardcoded host/port literals.
3. **Versioning via `VERSION.txt` (`0.0.1`) ONLY**:
   - Resolve version strictly via `AppConfig` (`GetVersion()` / `get_version()`); never read `APP_VERSION` or `SERVICE_VERSION` env overrides.
4. **Canonical 12 Log Levels (`flexible-logger` / `UniLog`)**:
   - Only `NOTSET` (0), `DEBUG` (1), `STREAM` (2), `INFO` (3), `LOGON` (4), `LOGOUT` (5), `TRADE` (6), `SCHEDULE` (7), `REPORT` (8), `WARNING` (9), `ERROR` (10), `CRITICAL` (11). Never use `WARN`, `CRIT`, `FATAL`, or `PANIC`.
5. **Always Use Standard `microservice-toolbox` Modules & Polyglot Local-First Workspace Resolution**:
   - Bootstrap with `BootstrapService` (Go) / `bootstrap_microservice` (Python) / `load_config` (Rust/C++), publish specs via `PublishWithLifecycle`, and expose `/api/v1/contracts`.
   - Service manifests MUST stay 100% CI/Docker-portable (zero local filesystem path pollution):
     - **Go (`go.work`)**: Declare canonical `github.com/Bastien-Antigravity/...` modules in `go.mod` (NEVER commit local `replace => ../...`). Local workspace development resolves sibling modules and new `*-toolbox` Go packages via workspace root `go.work`.
     - **Rust (`.cargo/config.toml`)**: Declare canonical `git = "https://github.com/Bastien-Antigravity/..."` dependencies in `Cargo.toml` (NEVER local `path = "../..."` or local `[patch]`). Workspace root `.cargo/config.toml` `paths = [...]` resolves local domain and core Rust crates automatically.
     - **Python (`bootstrap_microservice` & `_bastien_workspace.pth`)**: Declare canonical `git+https://github.com/Bastien-Antigravity/...` URLs in `requirements.txt` / `pyproject.toml` (NEVER `-e ../...` or `file://`). `bootstrap_microservice` and `.venv` `_bastien_workspace.pth` auto-discover local workspace `*-toolbox/python` and sibling SDK packages at runtime.
     - **C/C++ (`CMakeLists.txt` `FETCHCONTENT_SOURCE_DIR_*`)**: Declare `FetchContent_Declare(... GIT_REPOSITORY ...)` fallback in `CMakeLists.txt` (NEVER unconditional `add_subdirectory(../...)` or `/Users/...` paths). Before `FetchContent_MakeAvailable`, probe `$ENV{{BASTIEN_CORE_ROOT}}`, `$ENV{{BASTIEN_WORKSPACE_ROOT}}`, and parent directories to set `FETCHCONTENT_SOURCE_DIR_MICROSERVICE_TOOLBOX` and auto-discover any sibling `*-toolbox/cpp/CMakeLists.txt` (`FETCHCONTENT_SOURCE_DIR_<UPPER_NAME>`), adding local `libdistconf`/`libunilog`/`libnotif` `HINTS` automatically.
6. **Bastien Formatting & Language Standards**:
   - **Triple-Block Header** (`ESSENTIAL PROCESS`, `DATA FLOW`, `KEY PARAMETERS`) on all non-test source files + horizontal dividers (`77` dashes for Go/C++/SQL, `95` dashes for Python/Rust).
   - **Python**: Shebang + `# coding:utf-8`, granular camelCase stdlib/external aliases (`from os.path import join as osPathJoin`), single-line combined module imports, NO aliasing of local `src.*` imports, One-Class Rule, keyword-only `*` on >1 arg methods, and `self.logger.info(f"{{self.Name}} : {{msg}}")`.
   - **Go**: 4-block imports, idiomatic unprefixed nouns on both models and interfaces (`StatusPayload`, `Service`, `Logger` — no `M` or `I` prefixes), `GOPRIVATE=github.com/Bastien-Antigravity/*`.
   - **Anti-Drift (`11-Code-Doc`) & BDD (`02-Business-BDD`)**: Author `FEAT-*.md` specs in `{target_name}/02-Business-BDD/02-Behavior-Specs/<svc>/` before implementation and hand off to `@obsidian-brain:orchestrator` when coordinating cross-fleet changes.
"""
    create_file(workspace_dest / "AGENTS.md", workspace_agents_md, dry_run)

    # Root AI-CONTEXT.md
    workspace_ai_context_md = f"""---
microservice: {target_name}
type: context
status: active
tags:
- '#service/{target_name}'
- '#domain/context'
- '#type/context'
- '#state/active'
---

# AI-CONTEXT: {target_name} Domain Workspace

## Workspace Topology
- `./{target_name}/`: Pure domain knowledge vault
  - `00-AI-Orchestration/`: Domain DNA, session state, and initialization compass
  - `02-Business-BDD/02-Behavior-Specs/<svc>/FEAT-*.md`: Authoritative Gherkin behavior specs
  - `05-Fleet-Operation/00-Repo-Control/`: Domain `inventory.json` and `service-registry.json`
  - `06-Microservices/<svc>.md`: Markdown service hub specifications (docs only)
  - `07-Core-KMS/Role-Prompts/`: Custom domain agent personas (e.g. `20-DomainSpecialist`)
  - `11-Code-Doc/`: Anti-drift architectural documentation mirror
- `./<service-name>/`: Domain L3/L4/L5 microservice repositories (siblings of `./{target_name}/`), each symlinking `./standalone.yaml -> ../standalone.yaml`
- `./standalone.yaml`: Self-contained fleet endpoint profile for connecting to the central `Bastien-Antigravity` L1/L2 base fleet
- `./.cargo/config.toml`: Workspace-level Cargo `paths = [...]` local crate overrides (Rust equivalent of `go.work`, ignored in standalone CI/Docker)
- `./.agents/skills/`: Merged Antigravity IDE skills (central `Bastien-Antigravity` engineering skills + `{target_name}` domain personas)

## Polyglot Local-First Workspace Resolution (Zero Manifest Path Pollution)
Every service manifest (`go.mod`, `Cargo.toml`, `requirements.txt`/`pyproject.toml`, `CMakeLists.txt`) uses canonical GitHub references so standalone CI/Docker builds always succeed, while local workspace builds resolve sibling SDKs and newly added `*-toolbox` repositories automatically:
- **Go**: Workspace root `go.work` overrides `go.mod` module paths locally.
- **Rust**: Workspace root `.cargo/config.toml` `paths = [...]` overrides Git dependencies with local domain/core crates.
- **Python**: `bootstrap_microservice` and `.venv` `_bastien_workspace.pth` auto-discover local `*-toolbox/python` and sibling SDK directories before falling back to installed `git+https://` packages.
- **C/C++**: Generated `CMakeLists.txt` probes `$ENV{{BASTIEN_CORE_ROOT}}`, `$ENV{{BASTIEN_WORKSPACE_ROOT}}`, and parent folders to set `FETCHCONTENT_SOURCE_DIR_MICROSERVICE_TOOLBOX`, auto-discovers any sibling `*-toolbox/cpp/CMakeLists.txt` via `FETCHCONTENT_SOURCE_DIR_<UPPER_NAME>`, and falls back to GitHub `FetchContent_MakeAvailable` in CI/Docker.

## Base Fleet Endpoint Modes
Switch `./standalone.yaml` dynamically between native and Dockerized base L1/L2 fleets:
- **Local Native Fleet (`127.0.0.1`)**: `make switch-local`
- **Docker Host-Bridge Fleet (`127.0.0.2`)**: `make switch-docker`

## Cross-Brain BDD Handoff Workflow
1. Use domain personas (e.g., `@domainspecialist`) to draft domain specs in `./{target_name}/02-Business-BDD/02-Behavior-Specs/<svc>/FEAT-*.md` and hub docs in `./{target_name}/06-Microservices/<svc>.md`.
2. Hand off implementation, fleet verification, or central infrastructure changes to `@obsidian-brain:orchestrator` referencing the concrete `FEAT-*.md` path and this workspace directory.
3. Run compliance and scaffolding tooling directly from the central `Bastien-Antigravity` installation (`obsidian-brain/08-Squad-Agent/main.py`) without duplicating core scripts locally.
"""
    create_file(workspace_dest / "AI-CONTEXT.md", workspace_ai_context_md, dry_run)

    # Root Makefile (switch-local, switch-docker, docker-up, docker-down, status)
    workspace_makefile = f"""# External Domain Workspace Controller: {target_name}
.PHONY: switch-local switch-docker docker-up docker-down status

switch-local:
\t@python3 -c 'from pathlib import Path; p=Path("standalone.yaml"); t=p.read_text(encoding="utf-8").replace(":-127.0.0.2}}", ":-127.0.0.1}}").replace(":127.0.0.2}}", ":127.0.0.1}}"); p.write_text(t, encoding="utf-8")'
\t@echo "Switched ./standalone.yaml base fleet host to 127.0.0.1 (local native fleet)"

switch-docker:
\t@python3 -c 'from pathlib import Path; p=Path("standalone.yaml"); t=p.read_text(encoding="utf-8").replace(":-127.0.0.1}}", ":-127.0.0.2}}").replace(":127.0.0.1}}", ":127.0.0.2}}"); p.write_text(t, encoding="utf-8")'
\t@echo "Switched ./standalone.yaml base fleet host to 127.0.0.2 (docker host-bridge fleet)"

docker-up:
\tdocker compose up -d

docker-down:
\tdocker compose down

status:
\tdocker compose ps
"""
    create_file(workspace_dest / "Makefile", workspace_makefile, dry_run)

    # Root docker-compose.yaml (ZERO squad-agent, ZERO base L1/L2 containers)
    workspace_compose = f"""# =============================================================================
# Domain Workspace Compose: {target_name}
# Orchestrates ONLY this domain's L3/L4/L5 microservices on teleremote-network.
# Base L1/L2 services and squad-agent run centrally in Bastien-Antigravity.
# =============================================================================
services: {{}}

networks:
  teleremote-network:
    name: teleremote-network
    external: true
"""
    create_file(workspace_dest / "docker-compose.yaml", workspace_compose, dry_run)

    # 3. Seed pure domain vault files inside vault_dest
    seed_domain_repo_control(vault_dest, target_name, dry_run)
    create_file(vault_dest / "VERSION.txt", f"{active_version}\n", dry_run)

    dna_content = f"""---
microservice: {target_name}
type: governance
status: active
tags:
- '#service/{target_name}'
- '#type/governance'
- '#state/active'
- '#zone/0-orchestration'
---
# 🧬 AI Project DNA: {target_name}

## 🎯 High-Level Vision
Pure domain knowledge vault, behavioral specifications (`02-Business-BDD/`), microservice hubs (`06-Microservices/`), and anti-drift mirror (`11-Code-Doc/`) for `{target_name}`.

## 🛡️ Domain Isolation Rules
1. Keep domain documentation in `{target_name}/` and microservice repositories as sibling folders in `{workspace_dest.name}/`.
2. Never duplicate `08-Squad-Agent` or central `03-Tech-Stack` / `07-Core-KMS` templates inside this vault.
3. Maintain canonical YAML frontmatter (`microservice`, `type`, `status`, `tags`) on every vault markdown note.
"""
    create_file(vault_dest / "00-AI-Orchestration/AI-Project-DNA.md", dna_content, dry_run)

    session_content = f"""---
microservice: {target_name}
type: state
status: active
active-protocol: "🛡️ Mode 1: Spec-First"
tags:
- '#service/{target_name}'
- '#type/state'
- '#state/active'
- '#zone/0-orchestration'
---
# 🧠 AI Session State: {target_name}

## 🚀 Active Missions
- [ ] Author initial domain BDD behavior specs under `02-Business-BDD/02-Behavior-Specs/`.
- [ ] Scaffold sibling L3/L4/L5 microservices and hand off orchestration to `@obsidian-brain:orchestrator`.
"""
    create_file(vault_dest / "00-AI-Orchestration/AI-Session-State.md", session_content, dry_run)

    init_content = f"""---
microservice: {target_name}
type: governance
status: active
tags:
- '#service/{target_name}'
- '#type/governance'
- '#state/active'
- '#zone/0-orchestration'
---
# ⚡ AI Initialization: {target_name}

> [!IMPORTANT] MANDATORY INITIALIZATION
> 1. Read workspace rules in `../AGENTS.md` and `../AI-CONTEXT.md`.
> 2. Read the ecosystem map in **[[Ecosystem-Map-MOC]]**.
> 3. Load domain constraints from **[[AI-Project-DNA]]** and restore **[[AI-Session-State]]**.
"""
    create_file(vault_dest / "00-AI-Orchestration/AI-Init.md", init_content, dry_run)

    mode_content = "active_mode: 1\n\n# Mode Manual\n1: Spec-First\n2: Free-Labs\n3: Fleet-Commander\n"
    create_file(vault_dest / "00-AI-Orchestration/Config/MODE-MANUAL.md", mode_content, dry_run)

    moc_content = f"""---
microservice: {target_name}
type: moc
status: active
tags:
- '#service/{target_name}'
- '#type/moc'
- '#state/active'
- '#zone/0-orchestration'
---
# 🌌 {target_name}: Domain Knowledge Hub (MOC)

## 🤖 00 - AI Orchestration
- [[00-AI-Orchestration/AI-Project-DNA|🧬 AI Project DNA]]
- [[00-AI-Orchestration/AI-Init|⚡ AI Initialization]]
- [[00-AI-Orchestration/AI-Session-State|🧠 AI Session State]]

## 🧩 02 - Business BDD & 06 - Microservices
- `02-Business-BDD/02-Behavior-Specs/`: Gherkin feature specifications (`FEAT-*.md`)
- `06-Microservices/`: Markdown microservice specification hubs (code lives as sibling repos `../<svc>/`)
- `11-Code-Doc/`: Anti-drift code documentation mirror
"""
    create_file(vault_dest / "Ecosystem-Map-MOC.md", moc_content, dry_run)

    microservices_hub_readme = f"""---
microservice: {target_name}
type: documentation
status: active
tags:
- '#service/{target_name}'
- '#type/documentation'
- '#state/active'
---
# 📦 {target_name} Microservice Hubs

This folder stores **markdown specification hubs ONLY** (`<service-name>.md`).
Domain L3/L4/L5 microservice source repositories live as direct siblings of `{target_name}/` inside `{workspace_dest.name}/` (e.g. `../<service-name>/`), each linking `./standalone.yaml -> ../standalone.yaml`.
"""
    create_file(vault_dest / "06-Microservices/README.md", microservices_hub_readme, dry_run)

    code_doc_readme = f"""---
microservice: {target_name}
type: documentation
status: active
tags:
- '#service/{target_name}'
- '#type/documentation'
- '#state/active'
---
# 📚 Anti-Drift Code Documentation Mirror (`11-Code-Doc`)

Keep one mirror folder per domain microservice here so documentation stays synchronized with sibling service repositories (`../<service-name>/`).
"""
    create_file(vault_dest / "11-Code-Doc/README.md", code_doc_readme, dry_run)

    domain_specialist_prompt = f"""---
microservice: {target_name}
type: prompt
status: active
tags:
- '#service/{target_name}'
- '#type/prompt'
- '#state/active'
- '#agent/domain-specialist'
---
# Role: {target_name} Domain Specialist

## 🎯 Mission
You are the authoritative domain analyst and BDD architect for the `{target_name}` workspace.
Your responsibility is to translate domain requirements into unambiguous Gherkin specifications,
maintain microservice markdown hubs, and coordinate cross-brain implementation handoffs without
duplicating core `Bastien-Antigravity` infrastructure.

## 🛠️ Core Responsibilities
1. **Author BDD Feature Specs**:
   - Create `02-Business-BDD/02-Behavior-Specs/<service>/FEAT-NNN-<Title>.md` with concrete `Given / When / Then` scenarios and capability names.
2. **Maintain Microservice Hubs & Anti-Drift Docs**:
   - Keep `06-Microservices/<service>.md` linked to its `FEAT-*.md` specs and mirror architectural contracts in `11-Code-Doc/<service>/`.
3. **Cross-Brain Handoff (`@obsidian-brain:orchestrator`)**:
   - Once BDD specs are ready for implementation or fleet wiring, emit a structured handoff to `@obsidian-brain:orchestrator` citing:
     - Concrete `FEAT-*.md` spec paths inside `{target_name}/02-Business-BDD/02-Behavior-Specs/<service>/`
     - Sibling service repository path `{workspace_dest.name}/<service>/`
     - Target layer (`L3`/`L4`/`L5`), language (`go`/`python`/`rust`/`cpp`), and capability name.
"""
    create_file(
        vault_dest / "07-Core-KMS/Role-Prompts/20-DomainSpecialist/Prompt-DomainSpecialist.md",
        domain_specialist_prompt,
        dry_run,
    )

    # 4. Compile merged Antigravity IDE skills (central engineering + domain personas) into workspace_dest/.agents/skills
    logger.info("ScaffoldNewBrain : Compiling merged Antigravity IDE skills into .agents/skills...")
    if not dry_run:
        compile_skills(
            brain_dir=str(vault_dest),
            merge_core=True,
            out_dir=str(workspace_dest / ".agents" / "skills"),
            skip_workspace_link=True,
        )

    # 5. Non-fatally register workspace with 09-RAG-Engine
    if not dry_run:
        _register_workspace_with_rag(target_name, vault_dest, logger)

    logger.info(
        f"ScaffoldNewBrain : SUCCESS! External domain workspace ready at: {workspace_dest} "
        f"(vault: {vault_dest})"
    )

# -----------------------------------------------------------------------------------------------

def scaffold_brain(
    target_name: str,
    target_path: pathPath,
    vault_root: pathPath,
    dry_run: bool = False,
    launch_docker: bool = False,
    sa_port: typeOptional[int] = None,
    sa_grpc_port: typeOptional[int] = None,
    sandbox: bool = False,
    fleet_mode: str = "auto",
    workspace: bool = False
) -> None:
    """
    Executes complete scaffolding of a new Bastien-Antigravity brain vault.
    When workspace=True, delegates to scaffold_workspace() to fabricate a clean
    zero-mixing external domain workspace container.
    When sandbox=True, generates a self-contained standalone.yaml and isolated
    fleet inventory so testing never mutates live ecosystem files.
    """
    if workspace:
        scaffold_workspace(
            target_name,
            target_path,
            vault_root,
            dry_run=dry_run,
            sa_port=sa_port,
            sa_grpc_port=sa_grpc_port,
            fleet_mode=fleet_mode,
        )
        return
    mode_tag = " [ISOLATED SANDBOX]" if sandbox else ""
    logger.info(f"ScaffoldNewBrain : Fabricating '{target_name}'{mode_tag} at {target_path}...")

    # 0. Resolve non-colliding host ports for the satellite squad agent
    if sa_port is None or sa_grpc_port is None:
        auto_port, auto_grpc = resolve_available_ports(target_path)
        sa_port = sa_port or auto_port
        sa_grpc_port = sa_grpc_port or auto_grpc
    logger.info(f"ScaffoldNewBrain : Allocated ports -> HTTP: {sa_port}, gRPC: {sa_grpc_port}")

    # 1. Create Double-Digit Folder Hierarchy
    folders = [
        "00-AI-Orchestration",
        "01-Strategic-Nexus",
        "02-Business-BDD/02-Behavior-Specs",
        "03-Tech-Stack",
        "04-Rapid-Prototyping",
        "05-Fleet-Operation",
        "06-Microservices",
        "07-Core-KMS/Role-Prompts",
        "08-Squad-Agent",
        "11-Code-Doc",
        "99-Humans",
        "quick-overview",
    ]
    
    for folder in folders:
        d = target_path / folder
        if dry_run:
            logger.info(f"   [DRY-RUN] Would create directory: {d}")
        else:
            d.mkdir(parents=True, exist_ok=True)

    # 2. Copy "DNA" (Role Prompts, Squad-Agent, Governance Config, Repo Control & Tech Stack)
    logger.info("ScaffoldNewBrain : Copying AI Squad DNA...")
    common_ignore = shutilIgnorePatterns(".DS_Store", ".git*", "__pycache__", "*.pyc", "*.log")
    role_prompts_src = vault_root / "07-Core-KMS" / "Role-Prompts"
    if role_prompts_src.exists():
        dest_prompts = target_path / "07-Core-KMS" / "Role-Prompts"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {role_prompts_src} -> {dest_prompts}")
        else:
            shutilCopytree(role_prompts_src, dest_prompts, dirs_exist_ok=True, ignore=common_ignore)
    
    squad_agent_src = vault_root / "08-Squad-Agent"
    if squad_agent_src.exists():
        dest_scripts = target_path / "08-Squad-Agent"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {squad_agent_src} -> {dest_scripts}")
        else:
            shutilCopytree(
                squad_agent_src,
                dest_scripts,
                dirs_exist_ok=True,
                ignore=shutilIgnorePatterns(
                    ".venv*", "__pycache__", "*.pyc", ".pytest_cache*", ".git*",
                    "logs", "data", "standalone.yaml", ".DS_Store", "*.log",
                    ".shipper_offsets.json", "fs_data", "fs_temp"
                )
            )

    config_src = vault_root / "00-AI-Orchestration" / "Config"
    if config_src.exists():
        dest_config = target_path / "00-AI-Orchestration" / "Config"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {config_src} -> {dest_config}")
        else:
            shutilCopytree(config_src, dest_config, dirs_exist_ok=True, ignore=common_ignore)

    repo_control_src = vault_root / "05-Fleet-Operation" / "00-Repo-Control"
    if repo_control_src.exists():
        dest_repo_control = target_path / "05-Fleet-Operation" / "00-Repo-Control"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {repo_control_src} -> {dest_repo_control}")
        else:
            shutilCopytree(repo_control_src, dest_repo_control, dirs_exist_ok=True, ignore=common_ignore)

    templates_src = vault_root / "05-Fleet-Operation" / "04-Templates"
    if templates_src.exists():
        dest_templates = target_path / "05-Fleet-Operation" / "04-Templates"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {templates_src} -> {dest_templates}")
        else:
            shutilCopytree(templates_src, dest_templates, dirs_exist_ok=True, ignore=common_ignore)

    tech_stack_src = vault_root / "03-Tech-Stack"
    if tech_stack_src.exists():
        dest_tech_stack = target_path / "03-Tech-Stack"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {tech_stack_src} -> {dest_tech_stack}")
        else:
            shutilCopytree(tech_stack_src, dest_tech_stack, dirs_exist_ok=True, ignore=common_ignore)

    # 3. Create Root Ecosystem Files
    logger.info("ScaffoldNewBrain : Creating root ecosystem files...")
    
    # standalone.yaml: self-contained file in sandbox mode, resolved non-dangling symlink in standard mode
    use_docker_fleet = (
        fleet_mode == "docker"
        or (fleet_mode == "auto" and resolve_active_fleet_host(bootstrap.config) == "127.0.0.2")
    )
    if sandbox:
        isolated_yaml = generate_sandbox_standalone_yaml(vault_root, target_name, sa_port, sa_grpc_port, fleet_mode=fleet_mode)
        create_file(target_path / "standalone.yaml", isolated_yaml, dry_run)
        seed_sandbox_repo_control(target_path, target_name, sa_port, dry_run)
        config_link_doc = "standalone.yaml (Self-contained sandbox profile)"
    else:
        _, resolved_ws_root = resolve_vault_and_workspace(__file__)
        if use_docker_fleet:
            cfg_rel_parts = ("docker-deployment", "modes", "docker", "config", "host-bridge.yaml")
        else:
            cfg_rel_parts = ("docker-deployment", "modes", "local", "config", "native.yaml")
        fleet_candidates = [
            vault_root.parent.joinpath(*cfg_rel_parts),
            resolved_ws_root.joinpath(*cfg_rel_parts),
        ]
        fleet_yaml = next((c for c in fleet_candidates if c.is_file()), None)
        if fleet_yaml is not None:
            try:
                link_target = osPathRelpath(str(fleet_yaml), str(target_path.resolve()))
            except ValueError:
                link_target = str(fleet_yaml.resolve())
            create_symlink(target_path / "standalone.yaml", link_target, dry_run)
            config_link_doc = f"standalone.yaml -> {link_target}"
        else:
            isolated_yaml = generate_sandbox_standalone_yaml(vault_root, target_name, sa_port, sa_grpc_port, fleet_mode=fleet_mode)
            create_file(target_path / "standalone.yaml", isolated_yaml, dry_run)
            config_link_doc = "standalone.yaml (Self-contained generated profile)"

    # Point 08-Squad-Agent/standalone.yaml to the brain root's standalone.yaml when resolvable,
    # or write an isolated config copy if standalone.yaml is missing.
    if dry_run or (target_path / "standalone.yaml").exists():
        create_symlink(target_path / "08-Squad-Agent" / "standalone.yaml", "../standalone.yaml", dry_run)
    else:
        fallback_yaml = generate_sandbox_standalone_yaml(vault_root, target_name, sa_port, sa_grpc_port, fleet_mode=fleet_mode)
        create_file(target_path / "08-Squad-Agent" / "standalone.yaml", fallback_yaml, dry_run)

    # VERSION.txt
    active_version = bootstrap.config.get_version()
    create_file(target_path / "VERSION.txt", f"{active_version}\n", dry_run)

    # .gitignore
    gitignore_content = """# Environments
.venv/
env/
venv/
ENV/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.pytest_cache/

# IDE & OS
.DS_Store
.idea/
.vscode/
*.swp
*.swo

# Runtime Data
fs_data/
fs_temp/
*.log
"""
    create_file(target_path / ".gitignore", gitignore_content, dry_run)

    # AGENTS.md
    agents_md = f"""---
microservice: {target_name}
type: rules
status: active
tags:
- '#service/{target_name}'
- '#domain/knowledge'
- '#type/rules'
- '#state/active'
- '#zone/0-core'
---

# AGENTS.md: {target_name}

## Repository Mission & Architecture Role
`{target_name}` is an autonomous knowledge vault, domain intelligence engine, and pluggable satellite squad for the Bastien-Antigravity ecosystem.

- **Primary Structure**:
  - `00-AI-Orchestration`: Agent personas, coordination protocols, squad directives
  - `02-Business-BDD`: Domain glossary, BDD behavior specifications, acceptance criteria
  - `03-Tech-Stack`: Technical standards, networking protocols, domain blueprints
  - `06-Microservices`: Service specification sheets, endpoint registries, capability maps
  - `07-Core-KMS`: Operational prompts, key management references
  - `08-Squad-Agent`: AI squad operational engine room, CLI utilities (`main.py`)
- **Configuration Link**: `{config_link_doc}`

## Key Commands & Verification
```bash
# Start in Docker (Recommended - connects to fleet teleremote-network)
make up
# or
docker compose up -d

# Check status & logs
make status
make logs

# Scaffold an isolated microservice inside 06-Microservices/<name>
make scaffold-service NAME=order-engine LANG=go PORT=8190

# Stop container
make down

# Run locally in native Python
python3 08-Squad-Agent/main.py preflight-check
python3 08-Squad-Agent/main.py squad-agent
```

## AI Development & Integration Guidelines
1. **Never Contradict Architecture Blueprints**: Refer to `03-Tech-Stack/` before making cross-service design changes.
2. **Markdown Frontmatter Standard**: Every markdown file in this vault MUST begin with canonical YAML frontmatter (`microservice`, `type`, `status`, `tags`).
3. **Triple-Block Header in Code**: Any code script must adhere to the Triple-Block header (`ESSENTIAL PROCESS`, `DATA FLOW`, `KEY PARAMETERS`).
4. **Encrypted Credentials**: Never commit plaintext secrets to markdown notes or config files. Use `ENC(...)` tokens.
5. **No Broken Links**: Always use relative links or verified obsidian wikilinks.
"""
    create_file(target_path / "AGENTS.md", agents_md, dry_run)

    # README.md
    readme_content = f"""# 🧠 {target_name.replace('-', ' ').title()}

Bastien-Antigravity Ecosystem Knowledge Vault and Domain Orchestration Hub.

## 🚀 Quick Start
### Option A: Docker (Zero-Config, Plugs into Fleet)
```bash
make up       # Starts squad-agent on port {sa_port} connected to central teleremote-network
make logs     # Follow agent logs
make down     # Stop agent
```

### Option B: Native Python
```bash
python3 08-Squad-Agent/main.py preflight-check
python3 08-Squad-Agent/main.py squad-agent
```

### Option C: Scaffold & Develop New Microservices inside `{target_name}`
```bash
make scaffold-service NAME=order-engine LANG=go PORT=8190
```

## 📁 Vault Structure
- `00-AI-Orchestration`: AI squad coordination and session state
- `01-Strategic-Nexus`: Strategic objectives and anti-backlog
- `02-Business-BDD`: Domain specifications and Gherkin scenarios
- `03-Tech-Stack`: Architecture standards and protocols
- `06-Microservices`: Microservice hubs, registries, and domain service code
- `07-Core-KMS`: Security policies and squad role prompts
- `08-Squad-Agent`: Fleet management and scaffolding automation
"""
    create_file(target_path / "README.md", readme_content, dry_run)

    # docker-compose.yaml
    docker_compose_content = f"""# =============================================================================
# Satellite Brain Squad Agent Compose: {target_name}
# Pluggable autonomous agent workshop connecting to central teleremote-network.
# Configuration is sourced strictly from standalone.yaml (ecosystem standard).
# =============================================================================
services:
  squad-agent:
    build:
      context: ./08-Squad-Agent
      dockerfile: Dockerfile
    image: ghcr.io/bastien-antigravity/squad-agent:${{TAG:-develop}}
    container_name: squad-agent-${{BRAIN_ID:-{target_name}}}
    restart: unless-stopped
    ports:
      - "${{HOST_IP:-127.0.0.2}}:${{SA_PORT:-{sa_port}}}:${{SA_PORT:-{sa_port}}}"
      - "${{HOST_IP:-127.0.0.2}}:${{SA_GRPC_PORT:-{sa_grpc_port}}}:${{SA_GRPC_PORT:-{sa_grpc_port}}}"
    environment:
      - DOCKER_ENV=true
      - SA_IP=0.0.0.0
      - SQUAD_IP=0.0.0.0
      - SQUAD_PORT=${{SA_PORT:-{sa_port}}}
      - BRAIN_ID=${{BRAIN_ID:-{target_name}}}
      - TARGET_BRAIN_ID=${{BRAIN_ID:-{target_name}}}
      - OBSIDIAN_VAULT_PATH=/app/brain
      - BRAIN_DIR=/app/brain
      - WORKSPACE_ROOT=/workspace
      - CF_IP=config-server
      - CF_PORT=3306
      - LS_IP=log-server
      - LS_PORT=9020
      - SA_PORT=${{SA_PORT:-{sa_port}}}
      - SA_GRPC_PORT=${{SA_GRPC_PORT:-{sa_grpc_port}}}
      - TS_IP=timescale-db
      - TS_PORT=5432
      - TS_DBNAME=${{DB_NAME:-obsidiandb}}
      - TS_USER=${{DB_USER:-dbuser}}
      - TS_PASSWORD=${{DB_PASSWORD:-dbuser}}
      - NATS_IP=nats-server
      - NATS_PORT=4222
      - RG_IP=rag-engine
      - RG_PORT=8090
      - RG_GRPC_PORT=8091
      - RAG_PORT=8082
      - RG_REST_PORT=8093
      - WB_IP=web-interface
      - WB_PORT=5000
      - BASTIEN_PRIVATE_KEY_PATH=/etc/bastien/private.pem
      - GEMINI_API_KEY=${{GEMINI_API_KEY:-}}
      - GEMINI_MODEL=${{GEMINI_MODEL:-gemini-3.8-flash}}
      - DISCORD_BOT_TOKEN=${{DISCORD_BOT_TOKEN:-}}
      - DISCORD_CHANNEL_ID=${{DISCORD_CHANNEL_ID:-}}
    volumes:
      - ${{WORKSPACE_ROOT:-..}}:/workspace:rw
      - ./:/app/brain:rw
      - ./standalone.yaml:/app/standalone.yaml:ro
      - ./standalone.yaml:/app/brain/standalone.yaml:ro
      - ${{BASTIEN_PRIVATE_KEY_PATH:-/etc/bastien/private.pem}}:/etc/bastien/private.pem:ro
    networks:
      - teleremote-network
    labels:
      - com.centurylinklabs.watchtower.enable=false
      - ecosystem.antigravity.role=satellite-brain
      - ecosystem.antigravity.brain=${{BRAIN_ID:-{target_name}}}

networks:
  teleremote-network:
    name: teleremote-network
    external: true
"""
    create_file(target_path / "docker-compose.yaml", docker_compose_content, dry_run)

    # Makefile
    makefile_content = f"""# Satellite Brain Squad Agent Controller: {target_name}
NAME ?= sample-service
LANG ?= go
PORT ?= 8190

.PHONY: up down logs status restart build scaffold-service destroy-sandbox

up:
\tdocker compose up -d

down:
\tdocker compose down

logs:
\tdocker compose logs -f squad-agent

status:
\tdocker compose ps

restart:
\tdocker compose restart

build:
\tdocker compose build

scaffold-service:
\tpython3 08-Squad-Agent/main.py scaffold-microservice --sandbox --brain "$(CURDIR)" --name "$(NAME)" --lang "$(LANG)" --port "$(PORT)"

destroy-sandbox:
\tpython3 08-Squad-Agent/main.py scaffold-new-brain --destroy --name "{target_name}" --dest "$(CURDIR)"
"""
    create_file(target_path / "Makefile", makefile_content, dry_run)

    # 4. Generate Core Governance & Navigation Files
    logger.info("ScaffoldNewBrain : Generating Project Compass...")

    # 🧬 AI-Project-DNA.md
    dna_content = f"""---
microservice: {target_name}
type: governance
status: active
tags:
- '#service/{target_name}'
- '#type/governance'
- '#state/active'
- '#zone/0-orchestration'
---
# 🧬 AI Project DNA: {target_name}

## 🎯 High-Level Vision
Dedicated knowledge base, behavioral specifications, and domain orchestration hub for `{target_name}`.

## 🛡️ Core Constraints
1. **The [SCAN] Protocol**: Every response must start with a [SCAN] block.
2. **Double-Digit Hierarchy**: Maintain the 00-99 folder structure.
3. **Isolation Zones**: Keep human dashboards in `quick-overview/` and `99-Humans/` with `#ai/ignore`.
4. **Transversal Tags**: Every file must be classified via `#tech/`, `#tier/`, and `#zone/`.
"""
    create_file(target_path / "00-AI-Orchestration/AI-Project-DNA.md", dna_content, dry_run)

    # 🧠 AI-Session-State.md
    session_content = f"""---
microservice: {target_name}
type: state
status: active
active-protocol: "🛡️ Mode 1: Spec-First"
tags:
- '#service/{target_name}'
- '#type/state'
- '#state/active'
- '#zone/0-orchestration'
---
# 🧠 AI Session State: {target_name}

## 🚀 Active Missions
- [ ] Initialize domain specifications and microservice hubs.
"""
    create_file(target_path / "00-AI-Orchestration/AI-Session-State.md", session_content, dry_run)

    # ⚡ AI-Init.md
    init_content = f"""---
microservice: {target_name}
type: governance
status: active
tags:
- '#service/{target_name}'
- '#type/governance'
- '#state/active'
- '#zone/0-orchestration'
---
# ⚡ AI Initialization: {target_name}

> [!IMPORTANT] MANDATORY INITIALIZATION
> Copy and paste this prompt when starting a new session:
> 
> "1. Read the ecosystem map in **[[Ecosystem-Map-MOC]]**."
> "2. Load project constraints from **[[AI-Project-DNA]]**."
> "3. Restore session state from **[[AI-Session-State]]**."
"""
    create_file(target_path / "00-AI-Orchestration/AI-Init.md", init_content, dry_run)

    # 🗺️ Ecosystem-Map-MOC.md
    moc_content = f"""---
microservice: ecosystem-core
type: moc
status: active
tags:
- '#service/{target_name}'
- '#type/moc'
- '#state/active'
- '#zone/0-orchestration'
---
# 🌌 {target_name}: Master Knowledge Hub (MOC)

## 🤖 00 - AI Orchestration
- [[00-AI-Orchestration/AI-Project-DNA|🧬 AI Project DNA]]
- [[00-AI-Orchestration/AI-Init|⚡ AI Initialization]]
- [[00-AI-Orchestration/AI-Session-State|🧠 AI Session State]]
"""
    create_file(target_path / "Ecosystem-Map-MOC.md", moc_content, dry_run)

    # 00-AI-Orchestration/Config/MODE-MANUAL.md
    if not dry_run:
        (target_path / "00-AI-Orchestration" / "Config").mkdir(parents=True, exist_ok=True)
    mode_content = "active_mode: 1\n\n# Mode Manual\n1: Spec-First\n2: Free-Labs\n3: Fleet-Commander\n"
    create_file(target_path / "00-AI-Orchestration" / "Config" / "MODE-MANUAL.md", mode_content, dry_run)

    # quick-overview/00-Overview.md
    overview_content = f"""---
microservice: {target_name}
type: documentation
status: active
tags:
- '#service/{target_name}'
- '#type/documentation'
- '#state/active'
- '#ai/ignore'
---
# 📖 Overview: {target_name.replace('-', ' ').title()}

Human-readable overview and quick-start reference for this domain vault.
"""
    create_file(target_path / "quick-overview/00-Overview.md", overview_content, dry_run)

    # 5. Bake the AI Squad into the new ecosystem
    logger.info("ScaffoldNewBrain : Baking the AI Squad into the new ecosystem...")
    if not dry_run:
        env = osEnviron.copy()
        toolbox_py = vault_root.parent / "microservice-toolbox" / "python"
        if not toolbox_py.exists():
            for p in [vault_root] + list(vault_root.parents):
                candidate = p / "microservice-toolbox" / "python"
                if candidate.exists():
                    toolbox_py = candidate
                    break
        scripts_dir = target_path / "08-Squad-Agent"
        pythonpath_entries = [str(scripts_dir), str(scripts_dir / "src")]
        if toolbox_py.exists():
            pythonpath_entries.append(str(toolbox_py))
        if "PYTHONPATH" in env:
            pythonpath_entries.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = ":".join(pythonpath_entries)

        convert_script = scripts_dir / "main.py"
        if convert_script.exists():
            subprocessRun([sysExecutable, str(convert_script), "convert-agents", "--skip-workspace-link"], cwd=target_path, env=env)
        else:
            fallback_convert = scripts_dir / "src" / "fleet" / "convert_agents.py"
            if fallback_convert.exists():
                subprocessRun([sysExecutable, str(fallback_convert), "--skip-workspace-link"], cwd=target_path, env=env)

    # 6. Optional: Launch in Docker
    if launch_docker and not dry_run:
        launch_satellite_docker(target_path, target_name, sa_port)

    # 7. Non-fatally register workspace with 09-RAG-Engine
    if not dry_run:
        _register_workspace_with_rag(target_name, target_path, logger)

    logger.info(f"ScaffoldNewBrain : SUCCESS! Your new Command Center is ready at: {target_path}")

# -----------------------------------------------------------------------------------------------

def main() -> None:
    setup_terminal()
    vault_root, workspace_root = resolve_vault_and_workspace(__file__)

    parser = argparseArgumentParser(description="Bastien-Antigravity Ecosystem Scaffolder")
    parser.add_argument("--name", "-n", type=str, default="", help="New project name (e.g. trading-brain)")
    parser.add_argument("--dest", "-d", type=str, default="", help="Destination path (defaults to ../<name> or ../_sandbox/<name>)")
    parser.add_argument("--dry-run", action="store_true", help="Preview file fabrication without writing to disk")
    parser.add_argument("--docker", action="store_true", help="Automatically launch the newly scaffolded brain in Docker")
    parser.add_argument("--sandbox", "--isolated", dest="sandbox", action="store_true", help="Create an isolated sandbox brain with a self-contained standalone.yaml and isolated inventory")
    parser.add_argument("--workspace", action="store_true", default=False, help="Create a clean zero-mixing external domain workspace container (canonical default when --sandbox is False)")
    parser.add_argument("--legacy-satellite-copy", action="store_true", help="[DEPRECATED] Copy 08-Squad-Agent and 03-Tech-Stack into target directory instead of Zero-Mixing Workspace mode")
    parser.add_argument("--destroy", action="store_true", help="Destroy an isolated sandbox brain or domain workspace and purge its brain_id from RAG/PostgreSQL")
    parser.add_argument("--port", "-p", type=int, default=None, help="Explicit host HTTP port for squad-agent (defaults to auto-allocating 8185+)")
    parser.add_argument("--grpc-port", type=int, default=None, help="Explicit host gRPC port for squad-agent (defaults to port + 2)")
    parser.add_argument("--fleet-mode", choices=["auto", "local", "docker"], default="auto", help="Base fleet config target for standalone.yaml ('auto' probes active fleet, 'local' -> native.yaml 127.0.0.1, 'docker' -> host-bridge.yaml 127.0.0.2)")
    args = parser.parse_args()

    target_name = args.name.strip()
    if not target_name:
        try:
            target_name = input("Enter new project name (e.g. trading-brain): ").strip()
        except EOFError:
            target_name = ""

    if not target_name:
        logger.error("ScaffoldNewBrain : Project name is required.")
        return

    dest_input = args.dest.strip()
    if args.sandbox or args.destroy:
        default_target = (workspace_root / "_sandbox" / target_name).resolve()
    elif not args.legacy_satellite_copy:
        default_target = (workspace_root.parent / f"{target_name}-workspace").resolve()
    else:
        default_target = (workspace_root / target_name).resolve()

    if not dest_input:
        if args.sandbox or args.destroy or not args.legacy_satellite_copy:
            target_path = default_target
        else:
            try:
                dest_input = input(f"Enter destination path [default: {default_target}]: ").strip()
            except EOFError:
                dest_input = ""
            target_path = pathPath(dest_input).expanduser().resolve() if dest_input else default_target
    else:
        target_path = pathPath(dest_input).expanduser().resolve()

    if args.destroy:
        destroy_sandbox_brain(target_name, target_path, vault_root, dry_run=args.dry_run)
        return

    if target_path.exists() and not args.dry_run:
        logger.error(f"ScaffoldNewBrain : Path {target_path} already exists.")
        return

    use_workspace = not args.sandbox and not args.legacy_satellite_copy

    scaffold_brain(
        target_name,
        target_path,
        vault_root,
        dry_run=args.dry_run,
        launch_docker=args.docker,
        sa_port=args.port,
        sa_grpc_port=args.grpc_port,
        sandbox=args.sandbox,
        fleet_mode=args.fleet_mode,
        workspace=use_workspace,
    )

# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()

