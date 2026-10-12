---
microservice: base-scripts
type: note
status: active
tags:
- '#service/base-scripts'
- '#type/note'
- '#state/active'
- '#zone/3-fleet'
---

# 🧬 Project DNA: base-scripts

## Metadata
- Version: 0.0.1
- Classification: Level 1 Operational Engine & Governance Hub

## 🎯 High-Level Intent
- **Goal**: Operational engine room, autonomous AI squad coordinator, and fleet governance automation hub for the Bastien-Antigravity ecosystem.
- **Key Pattern**: Command-and-Control (C2) CLI router (`main.py`), OpenMFE Web server (port `8085`), gRPC control (port `8087`), and dynamic Telegram management.

## 🛠 Technical Constraints
- **Pattern**: Layered CLI subcommands (`COMMANDS_MAP`), Facade & Interface decoupling.
- **Bootstrap**: Initialized via `microservice-toolbox` Python bindings (`bootstrap_microservice`, `load_config`, `UniLog`).
- **Database**: PostgreSQL with schema isolation (`08-Squad-Agent` in `obsidiandb`).
- **Network**: Port `8085` (REST/OpenMFE), Port `8087` (gRPC SquadControl). Auto-registers MFE with `web-interface` on port `5000`.

## 👥 Roles & Responsibilities
- **Architect**: Maintain CLI modularity, fleet integrity, and port drift verification engines.
- **Developer**: Fulfill CLI commands, OpenMFE components, and test coverage.
- **QA**: Validate command execution, preflight checks, and mock isolation.

## 🚦 Lifecycle & Versioning
- **Primary Branch**: `develop`
- **Protected Branches**: `main`
- **Versioning Strategy**: Semantic Versioning (v0.0.1).
- **Version Source of Truth**: `VERSION.txt`.
