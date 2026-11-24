---
microservice: squad-agent
type: session-state
status: active
last-updated: 2026-09-16
Mission-ID: SQUAD-AGENT-AUDIT-2026-09-16
tags:
- '#tech/python'
- '#zone/3-fleet'
- '#service/squad-agent'
- '#type/session-state'
- '#state/active'
---

# 🛠️ Squad Agent - AI Session & State

## 🎯 Active Status
- **Current Mission**: Automated microservice scaffolding hardening, single source of truth inventory enforcement, and 21-agent squad coherence.
- **Scaffolding Generator**: `src/lifecycle/scaffold_microservice.py` provides explicit `[STARTER TEMPLATE / DUMMY ...]` banners in Python and Go, enforcing one-class rule, keyword-only constructors, typing.Protocol, StatusPayload dataclass, and pytest starter suites.
- **Coherence Verification**: `main.py check-coherence` verifies 100% coherence across all 21 agent skills and obsidian vault role prompts (with `[SCAN]` trailer deduplication in `convert_agents.py` and harmonized Go interface rules across `Go-Systems-Specialist.md` and `Prompt-Debloat-Sentinel.md`).
- **Preflight Verification**: `main.py preflight-check` ensures green state across essential files, submodules, modes, and inventories.
- **Single-Agent Read-Only Evaluation Harness (`2026-11-24`)**: Added `list_workspace_files`, role-scoped read-only tool permissions, `fold_bodies=False` default + folded-body write corruption guard in `src/agents/base_agent.py`, offline CLI `"minimal"` logger fast-path in `src/bootstrap/__init__.py`, positional `[path]` support in `src/auditing/debloat_audit.py`, and `main.py eval-agent` (`src/auditing/eval_agent.py` + `tests/test_eval_agent_readonly.py`).
