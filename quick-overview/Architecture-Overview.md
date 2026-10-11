---
microservice: base-scripts
type: overview
status: active
tags:
- '#service/base-scripts'
- '#type/overview'
- '#state/active'
- '#zone/3-fleet'
- '#ai/ignore'
---
# 🏗️ Architecture Overview: base-scripts

`08-Base-Scripts` is the operational command-and-control (C2) engine room, AI squad orchestrator, and fleet governance automation hub for the Bastien-Antigravity ecosystem.

## Subsystems

1. **Unified CLI Router (`main.py`)**:
   Central dispatcher mapping CLI aliases to themed packages (`auditing`, `fleet`, `lifecycle`, `maintenance`, `extraction`, `core`).

2. **Squad Command & Control (`src/core/`)**:
   - `start_squad.py`: Multi-agent orchestrator managing preflight checks, role compilation, event bus initialization, and daemon launching.
   - `controller.py`: `CommandController` executing subcommands, managing conversational short-term/PostgreSQL memory, and handling multi-channel chat (Web, Discord, Telegram).

3. **OpenMFE Web & REST Server (`src/web/`, `src/rest/`)**:
   - Exposes REST routes on port `8085` (`capabilities.base_scripts.port`).
   - Serves the OpenMFE micro-frontend (`/static/mfe.js`) and auto-registers with `web-interface` on port `5000` via `/api/v1/register`.

4. **gRPC SquadControl Service (`src/grpc_control/`)**:
   - Exposes `SquadControlService` on port `8087` (`capabilities.base_scripts.grpc_port`) for IPC status queries, subcommand execution, and mode switching.

5. **Auditing & Governance (`src/auditing/`)**:
   - `audit_ports.py`: 4-layer verification engine detecting port drift between `native.yaml`, `docker-compose.yaml`, `service-registry.json`, and markdown documentation.
   - `validate_compliance.py`: Mechanical invariant checker auditing shebangs, Triple-Block headers, section dividers, and mock absence.
   - `preflight_check.py`: System readiness gate verifying environment paths, dependencies, and configuration.
