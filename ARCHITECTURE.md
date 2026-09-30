---
microservice: obsidian-brain
type: automation
status: active
tags:
- '#service/obsidian-brain'
- '#type/automation'
- '#state/active'
- '#zone/3-fleet'
---

# 🏗️ Architecture: Base Scripts

The `08-Base-Scripts` repository follows a **Command-and-Control (C2)** architecture pattern designed for high-autonomy AI orchestration, compliance enforcement, and fleet management.

---

## 🧩 Component Map

### 1. The Core Orchestration Layer (`src/core/`)
- **`main.py`**: The unified CLI entry point router. Directs commands to categorized modules under `src/`.
- **`start_squad.py`**: The central squad orchestrator managing:
    1. **Preflight**: Validates inventory, modes, and configurations.
    2. **Sync**: Rebuilds runtime `.agents/` definitions from vault role prompts (`convert_agents.py`).
    3. **Protocol**: Locks the session into an active Mode (`switch_mode.py`).
    4. **Transit**: Connects via `DualSquadEventBus` to NATS (falling back to LocalEventBus).
    5. **Daemons**: Hosts FastAPI OpenMFE Web server, gRPC SquadControl, and dynamic Telegram controls.
- **`controller.py`**: The unified CommandController routing actions, status queries, and chat messages.

### 2. The Auditing & Compliance Layer (`src/auditing/`)
- **`validate_compliance.py`**: Mechanical code invariant auditor. Validates shebang/encoding, Triple-Block headers, section dividers, dynamic ports, and mock pollution.
- **`audit_ports.py`**: 4-Layer port drift verification engine ensuring zero drift across native.yaml, docker-compose, service-registry, and documentation.
- **`check_coherence.py`**: Ast-based check ensuring prompt synchronization between vault and runtime.
- **`ensure_frontmatter.py`**: Enforces strict YAML frontmatter and tag taxonomy across documentation.

### 3. The Fleet Layer (`src/fleet/`)
- **`fleet_commander.py`**: Operates at the workspace level, managing git state and processes across the microservices fleet.
- **`build_inventory.py`**: Generates `inventory.json` from workspace directories.

### 4. The Knowledge & Maintenance Layer (`src/maintenance/`, `src/extraction/`, `src/lib/`)
- **`persona_extractor.py`**: Uses AST (Python) and RegEx (Go/Rust) to build semantic telemetry maps of the codebase.
- **`knowledge_compressor.py`**: Distills recent session logs into structured architectural decision patterns.
- **`joint_audit_purger.py`**: Identifies dark matter orphan notes in the vault and generates deletion checklists.
- **`improved_transformer.py`**: AST-based compliance refactorer auto-repairing Python headers, dividers, and imports.

---

## 📡 Data Flow: Command Execution

1. **User / Agent** invokes `python3 main.py <command>`.
2. **`main.py`** resolves the module namespace via `src.bootstrap` and invokes target `main()`.
3. **`src.bootstrap`** loads layered configuration (`distributed-config`) and initializes `UniLog` logger singleton.
4. **Command Execution** performs operations dynamically respecting capability address resolution and ecosystem KMS encryption standards.
