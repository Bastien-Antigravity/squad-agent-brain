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
# 🕹️ Bastien-Antigravity: Squad Agent

This directory contains the core operational scripts and AI squad orchestration daemon for the Bastien-Antigravity AI Squad and Knowledge Management System (KMS). It acts as the "Engine Room" for the entire ecosystem.

---

## 🚀 Quick Start

### 1. Installation & Environment Setup
The scripts depend on the virtual environment located in the vault root.
```bash
# From the obsidian-brain root
pip install -r requirements.txt

# Export your GitHub token (mandatory for OpenMFE Web UI and REST API status)
export GITHUB_TOKEN="ghp_your_personal_access_token"
```

### 2. Launch the AI Squad
The primary entry point is the unified CLI router `main.py`. It initializes the environment, synchronizes personas, and launches your preferred AI client.
```bash
python3 08-Squad-Agent/main.py squad-agent
```

---

## 🛠️ Core Toolset (33 Commands)

All tools are unified under the `main.py` router (`python3 08-Squad-Agent/main.py <command>`):

| Command | Purpose |
| :--- | :--- |
| `squad-agent` | **Main Orchestrator**. Handles pre-session audits, role sync, event bus, and launches daemons. |
| `preflight-check` | **Preflight Gate**. Verifies essential files, submodules, inventory, modes, dynamic semver, and port drift. |
| `audit-ports` | **Port Invariant Auditor**. Checks 4 architectural layers for zero port drift. |
| `validate-compliance` | **Mechanical Code Compliance**. Verifies shebang/encoding, Triple-Block headers, dividers, ports, and mock pollution. |
| `format-compliance` | **Auto-Compliance Refactorer**. AST-based transformer repairing headers, dividers, and imports (`--fix`). |
| `check-coherence` | **Integrity Auditor**. Ensures runtime agent skills are 100% coherent with vault role prompts across 21 personas. |
| `ensure-frontmatter` | **Doc Taxonomist**. Enforces YAML frontmatter schema and tag taxonomy on markdown notes. |
| `hardening-yaml` | **YAML Hardener**. Enforces folder zone taxonomy rules on YAML configurations. |
| `build-inventory` | **Inventory Builder**. Scans workspace repositories and regenerates `05-Fleet-Operation/inventory.json`. |
| `fleet-commander` | **Fleet Manager**. Performs mass Git operations, status inspection, and branch tracking across fleet. |
| `fleet-refresh` | **Fleet Synchronizer**. Synchronizes local branches, submodules, and repository workspace state. |
| `fleet-init-update` | **Init Propagator**. Distributes standardized `AI-Init.md` instructions across fleet repositories. |
| `fleet-version` | **Semver Auditor**. Verifies dynamic semantic versioning across all 14 repositories against `VERSION.txt`. |
| `bump-version` | **Semver Bumper**. Increments semver (`patch`, `minor`, `major`) across fleet repositories. |
| `switch-mode` | **Protocol Switcher**. Atomically toggles between Spec-First, Labs, and Fleet modes. |
| `scaffold-microservice` | **Microservice Generator**. Generates standard Go, Rust, or Python microservices with all 12 root files. |
| `scaffold-new-brain` | **Vault Generator**. Creates new repositories or vault structures following standard DNA. |
| `init-new-brain` | **Vault Reset**. Resets project variables, purges inbox tasks, and initializes session state. |
| `unlock-vault` | **KMS Unlocker**. Removes KMS lock protections on sensitive vault files for updates. |
| `install-git-hooks` | **Git Hooks Installer**. Registers Git hooks to validate file syntax and frontmatter alignment. |
| `mission-help` | **Help System**. Displays detailed subcommand usage and structural layout guides. |
| `agent-dispatcher` | **Task Dispatcher**. Routes tasks to specific AI agent personas based on frontmatter or semantic keywords. |
| `controller` | **Command Router**. Manages backend execution, subprocess spawning, and memory coordination. |
| `discord-client` | **Discord Client**. Connects Discord chat channels to the unified squad command controller. |
| `map-feats` | **BDD Feature Mapper**. Crawls specifications to map microservices to behavioral feature files. |
| `fix-feats` | **BDD Feature Normalizer**. Standardizes BDD spec files with missing domain tags and hub links. |
| `close-mission` | **Mission Sign-off**. Validates git branches, dirty repositories, and session sign-off seal. |
| `convert-agents` | **Persona Compiler**. Compiles 21 role prompts from KMS/Nexus into runtime Antigravity skills. |
| `brain-health-audit` | **Vault Health Audit**. Scans notes for missing links, broken tags, and orphaned files. |
| `knowledge-compressor` | **Memory Distiller**. Distills recent session logs into structured decision patterns. |
| `persona-extractor` | **RAG Telemetry Helper**. Scans codebase metrics (Go, Rust, Python) for AI context. |
| `joint-audit-purger` | **Dark Matter Purger**. Identifies orphan notes without links and generates deletion checklists. |
| `maintenance-skill` | **System Maintenance**. Runs routine index checks, compacts databases, and audits system metadata. |

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

- **Preflight Checks**: `main.py squad-agent` runs a mandatory audit before every session.
- **Mode Guardrails**: Enforcement of `MODE-MANUAL.md` rules is handled by `switch-mode`.
- **Hard-Stop State**: Every session-ending script updates `AI-Session-State.md` to prevent context loss.

---

## 🤝 Contributing
See [[CONTRIBUTING]] for guidelines on adding new scripts or clients to the engine room.
