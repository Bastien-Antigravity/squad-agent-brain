---
microservice: obsidian-brain
type: automation
status: active
tags:
- '#service/obsidian-brain'
- '#type/automation'
- '#state/active'
- '#zone/3-fleet'
- '#ai/ignore'
---
# 🕹️ Bastien-Antigravity: Base Scripts

This directory contains the core operational scripts for the Bastien-Antigravity AI Squad and Knowledge Management System (KMS). It acts as the "Engine Room" for the entire ecosystem.

---

## 🚀 Quick Start

### 1. Installation
The scripts depend on the virtual environment located in the vault root.
```bash
# From the obsidian-brain root
pip install -r requirements.txt
```

### 2. Launch the AI Squad
The primary entry point is the unified CLI router `main.py`. It initializes the environment, synchronizes personas, and launches your preferred AI client.
```bash
python3 08-Base-Scripts/main.py start-squad
```

---

## 🛠️ Core Toolset

All tools are unified under the `main.py` router:

| Command | Purpose |
| :--- | :--- |
| `python3 08-Base-Scripts/main.py start-squad` | **Main Orchestrator**. Handles pre-session audits, role sync, event bus, and launches daemons. |
| `python3 08-Base-Scripts/main.py preflight-check` | **Preflight Gate**. Verifies essential files, submodules, inventory, modes, and port drift. |
| `python3 08-Base-Scripts/main.py audit-ports` | **Port Invariant Auditor**. Checks 4 architectural layers for zero port drift. |
| `python3 08-Base-Scripts/main.py validate-compliance` | **Mechanical Code Compliance**. Verifies shebang/encoding, Triple-Block headers, dividers, ports, and mock pollution. |
| `python3 08-Base-Scripts/main.py format-compliance` | **Auto-Compliance Refactorer**. AST-based transformer repairing headers, dividers, and imports (`--fix`). |
| `python3 08-Base-Scripts/main.py build-inventory` | **Inventory Builder**. Scans workspace repositories and regenerates `inventory.json`. |
| `python3 08-Base-Scripts/main.py fleet-commander` | **Fleet Manager**. Performs mass Git operations, status inspection, and branch tracking across fleet. |
| `python3 08-Base-Scripts/main.py switch-mode` | **Protocol Switcher**. Atomically toggles between Spec-First, Labs, and Fleet modes. |
| `python3 08-Base-Scripts/main.py check-coherence` | **Integrity Auditor**. Ensures runtime agent skills are 100% coherent with vault prompts. |
| `python3 08-Base-Scripts/main.py ensure-frontmatter` | **Doc Taxonomist**. Enforces YAML frontmatter schema and tag taxonomy on markdown notes. |
| `python3 08-Base-Scripts/main.py persona-extractor` | **RAG Telemetry Helper**. Scans codebase metrics (Go, Rust, Python) for AI context. |
| `python3 08-Base-Scripts/main.py knowledge-compressor` | **Memory Distiller**. Distills recent session logs into structured decision patterns. |
| `python3 08-Base-Scripts/main.py scaffold-microservice` | **Scaffolder**. Generates standard-compliant Go, Rust, or Python microservices with full scaffolding. |
| `python3 08-Base-Scripts/main.py scaffold-new-brain` | **Vault Generator**. Creates new repositories or vault structures following standard DNA. |
| `python3 08-Base-Scripts/main.py joint-audit-purger` | **Dark Matter Purger**. Identifies orphan notes without links and generates deletion checklists. |

---

## 📁 Directory Structure

- **`src/core/`**: Orchestration entry points (`start_squad.py`, `controller.py`, `switch_mode.py`).
- **`src/auditing/`**: Verification and compliance tools (`audit_ports.py`, `validate_compliance.py`, `preflight_check.py`, `check_coherence.py`, `ensure_frontmatter.py`).
- **`src/fleet/`**: Multi-repository management (`fleet_commander.py`, `build_inventory.py`, `fix_feats.py`, `map_feats.py`, `close_mission.py`).
- **`src/lifecycle/`**: Scaffolding, initialization, and hooks (`scaffold_microservice.py`, `scaffold_new_brain.py`, `unlock_vault.py`, `install_git_hooks.py`).
- **`src/maintenance/`**: Vault cleanup and pattern distillation (`joint_audit_purger.py`, `knowledge_compressor.py`).
- **`src/lib/`**: AST transformer, PostgreSQL connection pool, memory stores, and `Sovereignty` engine.
- **`src/interfaces/`**: Event bus (`DualSquadEventBus`, `LocalEventBus`) and abstract contracts.
- **`src/web/`, `src/rest/`, `src/grpc_control/`, `src/telegram/`**: Control interfaces and OpenMFE host.

---

## 🛡️ Governance & Safety
Most scripts include a **Bootstrap** phase that resolves the vault root and ensures the correct Python environment and library paths are loaded.

- **Preflight Checks**: `main.py start-squad` runs a mandatory audit before every session.
- **Mode Guardrails**: Enforcement of `MODE-MANUAL.md` rules is handled by `switch-mode`.
- **Hard-Stop State**: Every session-ending script updates `AI-Session-State.md` to prevent context loss.

---

## 🤝 Contributing
See [[CONTRIBUTING]] for guidelines on adding new scripts or clients to the engine room.
