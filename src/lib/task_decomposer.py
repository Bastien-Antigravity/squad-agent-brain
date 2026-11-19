#!/usr/bin/env python
# coding:utf-8
# strict:imports
# strict:lean

"""
ESSENTIAL PROCESS:
TaskDecomposer — Deterministic Complexity Gate and Micro-Task Splitter for the AI Squad.
Evaluates incoming user prompts across blast radius (file count), architectural layer span,
polyglot scope, and action density to prevent context drift on fast models (e.g., gemini-3.8-flash).

DATA FLOW:
1. Input:   Raw user request or mission description string.
2. Logic:   Scores complexity (1..10), identifies target files/layers/languages, and generates
            atomic sequential micro-steps with injected canonical microservice-toolbox reminders.
3. Output:  Structured decomposition dictionary and formatted markdown execution plan.

KEY PARAMETERS:
- max_files_per_turn: Maximum files an agent should modify in a single turn (default: 2).
- split_threshold:    Complexity score threshold triggering mandatory task splitting (default: 4).
"""

from re import IGNORECASE as reIGNORECASE, findall as reFindall, search as reSearch
from typing import Any as typeAny, Dict as typeDict, List as typeList

# -----------------------------------------------------------------------------------------------

LAYER_KEYWORDS: typeDict[str, typeList[str]] = {
    "config_and_contracts": [
        "standalone.yaml", "native.yaml", "appconfig", "capability", "capabilities",
        "proto", "capnp", "openmfe", "contract", "version.txt",
    ],
    "storage_and_db": [
        "postgres", "timescale", "sql", "schema", "migration", "table", "query",
        "pgvector", "embeddings", "memory",
    ],
    "core_engine": [
        "controller", "agent", "orchestrator", "algorithm", "transformer", "ast",
        "concurrency", "task", "lifecycle", "autorepair",
    ],
    "transport_and_api": [
        "rest", "fastapi", "endpoint", "grpc", "nats", "event_bus", "safesocket",
        "sse", "stream", "webhook", "http",
    ],
    "ui_and_clients": [
        "web-interface", "mfe", "telegram", "discord", "dashboard", "frontend", "ui",
    ],
    "verification_and_docs": [
        "pytest", "unittest", "go test", "cargo test", "bdd", "feat-", "compliance",
        "debloat", "doc", "blueprint", "obsidian",
    ],
}

LANGUAGE_PATTERNS: typeDict[str, str] = {
    "python": r"\b(\.py|python|pytest|fastapi|asyncio)\b",
    "go": r"\b(\.go|golang|go\s+test|goroutine)\b",
    "rust": r"\b(\.rs|rust|cargo|tokio)\b",
    "cpp": r"\b(\.cpp|\.hpp|c\+\+|cmake)\b",
    "sql": r"\b(\.sql|postgres|timescaledb|select|insert)\b",
}

CANONICAL_TOOLBOX_REMINDERS: typeList[str] = [
    "Version Resolution: ALWAYS call `config.get_version()` (Python) or `appConfig.GetVersion()` (Go). NEVER scan parent directories for `VERSION.txt`.",
    "Dynamic Networking: ALWAYS call `config.get_listen_addr(cap)`, `config.get_grpc_listen_addr(cap)`, or `config.get_rest_addr(cap)`. NEVER hardcode `127.0.0.1` or ports.",
    "Single Config Source: Read settings from `config.get_capability('<service>')`. NEVER chain `os.getenv()` fallbacks in business logic (`standalone.yaml` expands `${VAR:default}` at boot).",
    "Zero Config Paranoia: Trust `bootstrap_microservice` / `BootstrapService`. NEVER write `hasattr(self.config, ...)` or `isinstance(self.config.data, dict)` on hot paths.",
    "Safe-by-Design Concurrency: NEVER wrap Go `atomic.*` in `sync.Mutex`, NEVER use `asyncio.Lock` without an inner `await`, and NEVER write `os.path.exists()` before `open()` (TOCTOU).",
    "Strong Task References: Store every `asyncio.create_task()` / `loop.create_task()` in a strong reference set (`register_background_task`).",
    "Obsidian Alignment: Bind core controllers and interfaces with `@obsidian [[Doc-Title]]` and keep `03-Tech-Stack/` blueprints synchronized.",
]

# -----------------------------------------------------------------------------------------------


class TaskDecomposer:
    """
    @obsidian [[15-Safe-By-Design-Invariants]]
    Evaluates prompt complexity and splits multi-layer or multi-file requests into
    atomic, high-accuracy micro-steps suitable for single-turn execution.
    """

    Name = "TaskDecomposer"

    def __init__(self, *, max_files_per_turn: int = 2, split_threshold: int = 4) -> None:
        self.max_files_per_turn = max_files_per_turn
        self.split_threshold = split_threshold

    # -----------------------------------------------------------------------------------------------

    def evaluate_complexity(self, prompt: str) -> typeDict[str, typeAny]:
        """Computes a deterministic complexity breakdown for a user request."""
        text = (prompt or "").strip()
        lower_text = text.lower()

        # 1. Extract explicit file paths/names mentioned in the prompt
        raw_files = reFindall(
            r"[A-Za-z0-9_./-]+\.(?:py|go|rs|cpp|hpp|h|md|yaml|yml|json|proto|sql)",
            text,
        )
        detected_files: typeList[str] = []
        for f in raw_files:
            clean_f = f.strip(".,:;()[]{}\"'")
            if clean_f and clean_f not in detected_files:
                detected_files.append(clean_f)

        # 2. Detect architectural layers touched
        detected_layers: typeList[str] = []
        for layer_name, keywords in LAYER_KEYWORDS.items():
            if any(kw in lower_text for kw in keywords):
                detected_layers.append(layer_name)

        # 3. Detect programming languages involved
        detected_languages: typeList[str] = []
        for lang, pattern in LANGUAGE_PATTERNS.items():
            if reSearch(pattern, lower_text, reIGNORECASE):
                detected_languages.append(lang)

        # 4. Count distinct action verbs / clauses
        action_matches = reFindall(
            r"\b(implement|refactor|fix|add|remove|migrate|audit|test|update|create|scaffold|sync|verify|enforce)\b",
            lower_text,
        )
        distinct_actions = sorted(list(set(action_matches)))

        is_fleet_wide = bool(
            reSearch(r"\b(fleet|all\s+repos|all\s+services|across\s+the\s+ecosystem|every\s+microservice)\b", lower_text)
        )

        # Compute deterministic score (1..10)
        score = 1
        score += min(len(detected_files), 4)
        score += max(0, len(detected_layers) - 1)
        score += max(0, len(detected_languages) - 1) * 2
        if len(distinct_actions) >= 3:
            score += 1
        if is_fleet_wide:
            score += 2
        if len(text) > 700:
            score += 1
        score = min(score, 10)

        requires_split = (
            score >= self.split_threshold
            or len(detected_files) > self.max_files_per_turn
            or len(detected_layers) > 2
            or len(detected_languages) > 1
            or is_fleet_wide
        )

        return {
            "complexity_score": score,
            "classification": "MULTI_STEP_REQUIRED" if requires_split else "ATOMIC",
            "requires_split": requires_split,
            "detected_files": detected_files,
            "detected_layers": detected_layers or ["core_engine"],
            "detected_languages": detected_languages or ["python"],
            "distinct_actions": distinct_actions,
            "is_fleet_wide": is_fleet_wide,
        }

    # -----------------------------------------------------------------------------------------------

    def decompose_request(self, prompt: str) -> typeDict[str, typeAny]:
        """
        Evaluates a request and decomposes it into ordered atomic micro-steps
        with targeted ecosystem guardrail reminders.
        """
        analysis = self.evaluate_complexity(prompt)
        files = analysis["detected_files"]
        layers = analysis["detected_layers"]
        subtasks: typeList[typeDict[str, typeAny]] = []

        if not analysis["requires_split"]:
            subtasks.append({
                "step": 1,
                "layer": layers[0],
                "target_files": files[: self.max_files_per_turn],
                "objective": "Execute atomic change and verify with `validate_compliance` (strict_imports + strict_lean).",
            })
        else:
            step_num = 1
            # Step A: Configuration & Contracts first (if applicable)
            if "config_and_contracts" in layers or "storage_and_db" in layers:
                cfg_files = [f for f in files if f.endswith((".yaml", ".yml", ".proto", ".sql", ".json"))]
                subtasks.append({
                    "step": step_num,
                    "layer": "config_and_contracts",
                    "target_files": cfg_files[: self.max_files_per_turn],
                    "objective": (
                        "Align canonical configuration keys in `standalone.yaml` / `AppConfig` and schema contracts "
                        "(zero hardcoded ports, single canonical field name, fail-fast cold-path validation)."
                    ),
                })
                step_num += 1

            # Step B: Chunk implementation files in batches of at most `max_files_per_turn`
            code_files = [f for f in files if not f.endswith((".yaml", ".yml", ".proto", ".sql", ".md")) and "test" not in f]
            if code_files:
                for idx in range(0, len(code_files), self.max_files_per_turn):
                    batch = code_files[idx : idx + self.max_files_per_turn]
                    subtasks.append({
                        "step": step_num,
                        "layer": "core_engine",
                        "target_files": batch,
                        "objective": (
                            f"Implement core logic in {', '.join(batch)} using canonical `microservice-toolbox` APIs "
                            "and Bastien granular camelCase imports. Run `validate_compliance --strict-lean` immediately."
                        ),
                    })
                    step_num += 1
            else:
                for layer in layers:
                    if layer in ("config_and_contracts", "verification_and_docs"):
                        continue
                    subtasks.append({
                        "step": step_num,
                        "layer": layer,
                        "target_files": [],
                        "objective": (
                            f"Implement changes isolated to the `{layer}` layer (max {self.max_files_per_turn} files per turn) "
                            "adhering strictly to `15-Safe-By-Design-Invariants.md`."
                        ),
                    })
                    step_num += 1

            # Step C: Final Verification, Debloat Gate & Documentation Sync
            test_and_doc_files = [f for f in files if "test" in f or f.endswith(".md")]
            subtasks.append({
                "step": step_num,
                "layer": "verification_and_docs",
                "target_files": test_and_doc_files[: self.max_files_per_turn],
                "objective": (
                    "Run unit tests (`pytest` / `go test`), execute `validate_compliance --strict-imports --strict-lean`, "
                    "and synchronize `@obsidian [[...]]` links and `03-Tech-Stack/` documentation."
                ),
            })

        return {
            **analysis,
            "subtasks": subtasks,
            "canonical_toolbox_reminders": list(CANONICAL_TOOLBOX_REMINDERS),
        }

    # -----------------------------------------------------------------------------------------------

    def format_execution_plan(self, prompt: str) -> str:
        """Formats the decomposition result as an actionable markdown directive for the LLM context."""
        plan = self.decompose_request(prompt)
        lines = [
            f"### 🧭 Complexity Gate Assessment: `{plan['classification']}` (Score: {plan['complexity_score']}/10)",
            f"- **Detected Layers**: `{', '.join(plan['detected_layers'])}`",
            f"- **Detected Languages**: `{', '.join(plan['detected_languages'])}`",
        ]
        if plan["detected_files"]:
            lines.append(f"- **Target Files ({len(plan['detected_files'])})**: `{', '.join(plan['detected_files'])}`")

        lines.append("\n#### 🛠️ Mandatory Micro-Step Execution Plan (Execute Sequentially — Max 2 Files/Turn):")
        for task in plan["subtasks"]:
            files_str = f" (`{', '.join(task['target_files'])}`)" if task["target_files"] else ""
            lines.append(f"{task['step']}. **[{task['layer']}]**{files_str}: {task['objective']}")

        lines.append("\n#### 🛡️ Non-Negotiable Ecosystem & Anti-Bloat Guardrails:")
        for rem in plan["canonical_toolbox_reminders"]:
            lines.append(f"- {rem}")

        return "\n".join(lines)

