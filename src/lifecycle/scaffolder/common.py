#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Shared filesystem helpers, workspace/Cargo/Go-work registration utilities, OpenMFE Web
Component bundle builder, multi-stage Docker/CI/Makefile common file generator, and BDD
specification emitter for Bastien-Antigravity microservice scaffolding.

DATA FLOW:
1. Input: Target service directory, service slug, language, port, layer, and brain path.
2. Logic: Resolves workspace boundaries, renders portable Dockerfiles/workflows/CMakeLists,
   emits Gherkin BDD specs, and updates domain standalone.yaml + inventory registries.
3. Output: Standardized cross-language repository infrastructure files.

KEY PARAMETERS:
- target_dir: Destination repository directory for the scaffolded microservice.
- name: Kebab-case microservice identifier.
- lang: Target implementation language ('go', 'python', 'rust', 'cpp').
"""

from json import dumps as jsonDumps, loads as jsonLoads
from os import environ as osEnviron, symlink as osSymlink
from os.path import relpath as osPathRelpath
from pathlib import Path as pathPath
from re import DOTALL as reDotAll, findall as reFindall, search as reSearch, sub as reSub
from typing import Any as typeAny, List as typeList, Optional as typeOptional, Set as typeSet

# -----------------------------------------------------------------------------------------------

_logger: typeAny = None


def _get_logger() -> typeAny:
    """Lazily resolves the 08-Squad-Agent UniLog singleton from src.bootstrap."""
    global _logger
    if _logger is None:
        import src.bootstrap as bootstrap
        _logger = bootstrap.logger
    return _logger


# -----------------------------------------------------------------------------------------------

def resolve_workspace_root() -> pathPath:
    """Resolves the active workspace root dynamically without hardcoded folder names."""
    def _is_valid_workspace(candidate: pathPath) -> bool:
        return (
            (candidate / "docker-deployment" / "modes" / "local" / "config" / "native.yaml").is_file()
            and (candidate / "microservice-toolbox" / "python").is_dir()
        )

    core_root_env = osEnviron.get("BASTIEN_CORE_ROOT", "").strip()
    if core_root_env:
        env_candidate = pathPath(core_root_env).expanduser().resolve()
        if _is_valid_workspace(env_candidate):
            return env_candidate

    current = pathPath(__file__).resolve()
    ancestors = [current] + list(current.parents)

    for parent in ancestors:
        if _is_valid_workspace(parent):
            return parent

    for parent in ancestors:
        try:
            subdirs = list(parent.iterdir())
        except OSError:
            continue
        for s in subdirs:
            if s.is_dir() and _is_valid_workspace(s):
                return s

    for parent in ancestors:
        try:
            if any(parent.glob("*.code-workspace")):
                return parent
        except OSError:
            continue

    return pathPath.cwd()
# -----------------------------------------------------------------------------------------------

def create_file(path: pathPath, content: str, dry_run: bool = False) -> None:
    """Creates a file with parent directory creation, respecting dry-run mode."""
    if dry_run:
        _get_logger().info(f"Scaffolder : [DRY-RUN] Would create file: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    _get_logger().info(f"Scaffolder : ✅ Created: {path}")
# -----------------------------------------------------------------------------------------------

def create_symlink(target_path: pathPath, link_target: str, dry_run: bool = False) -> None:
    """Creates a symbolic link, respecting dry-run mode."""
    if dry_run:
        _get_logger().info(f"Scaffolder : [DRY-RUN] Would symlink: {target_path} -> {link_target}")
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.is_symlink() or target_path.exists():
        target_path.unlink()
    osSymlink(link_target, target_path)
    _get_logger().info(f"Scaffolder : 🔗 Symlinked: {target_path} -> {link_target}")
# -----------------------------------------------------------------------------------------------

def _is_core_workspace(target_dir: pathPath, workspace_root: pathPath) -> bool:
    """Returns True when target_dir resides inside the local core Bastien-Antigravity workspace."""
    if pathPath("/workspace/microservice-toolbox").exists() and str(target_dir).startswith("/app"):
        return True
    return (
        (workspace_root / "microservice-toolbox").exists()
        and target_dir.resolve().is_relative_to(workspace_root.resolve())
    )
# -----------------------------------------------------------------------------------------------

def _register_in_go_work(workspace_root: pathPath, target_dir: pathPath) -> None:
    """Ensures a newly scaffolded Go microservice is registered in the workspace go.work file."""
    go_work_path = workspace_root / "go.work"
    if not go_work_path.is_file():
        return

    try:
        rel_path = target_dir.resolve().relative_to(workspace_root.resolve()).as_posix()
        entry = f"./{rel_path}"
        content = go_work_path.read_text(encoding="utf-8")
        if entry in content:
            return

        if "use (" in content:
            lines = content.splitlines()
            new_lines = []
            inserted = False
            for line in lines:
                if line.strip() == ")" and not inserted:
                    new_lines.append(f"\t{entry}")
                    inserted = True
                new_lines.append(line)
            if inserted:
                go_work_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                _get_logger().info(f"Scaffolder : 🔗 Registered in {go_work_path.name}: {entry}")
    except Exception as e:
        _get_logger().warning(f"Scaffolder : Could not register in go.work: {e}")
# -----------------------------------------------------------------------------------------------

def _discover_rust_library_crates(workspace_root: pathPath) -> typeList[str]:
    """Scans workspace_root for local Rust library crates (Cargo.toml + src/lib.rs)."""
    ignored_dirs = {".git", ".cargo", ".venv", "venv", "target", "node_modules", "04-Rapid-Prototyping"}
    crates: typeList[str] = []
    seen: typeSet[str] = set()
    resolved_ws = workspace_root.resolve()
    try:
        repos = sorted(resolved_ws.iterdir())
    except OSError:
        return crates

    for repo in repos:
        if not repo.is_dir() or repo.name.startswith(".") or repo.name in ignored_dirs:
            continue
        for pat in ("Cargo.toml", "rust/Cargo.toml", "*/rust/Cargo.toml"):
            for cargo_toml in sorted(repo.glob(pat)):
                crate_dir = cargo_toml.parent
                if (crate_dir / "src" / "lib.rs").is_file():
                    rel_posix = crate_dir.resolve().relative_to(resolved_ws).as_posix()
                    if rel_posix not in seen:
                        seen.add(rel_posix)
                        crates.append(rel_posix)
    return crates
# -----------------------------------------------------------------------------------------------

def _register_in_cargo_config(workspace_root: pathPath, target_dir: pathPath) -> None:
    """
    Scans workspace_root for local Rust library crates (<repo>/Cargo.toml, <repo>/rust/Cargo.toml,
    <repo>/*/rust/Cargo.toml where src/lib.rs exists) and ensures they are registered in
    workspace_root / '.cargo' / 'config.toml'.
    """
    cargo_config_path = workspace_root / ".cargo" / "config.toml"
    discovered = _discover_rust_library_crates(workspace_root)

    try:
        resolved_target = target_dir.resolve()
        resolved_ws = workspace_root.resolve()
        if (
            resolved_target.is_relative_to(resolved_ws)
            and (resolved_target / "Cargo.toml").is_file()
            and (resolved_target / "src" / "lib.rs").is_file()
        ):
            target_rel = resolved_target.relative_to(resolved_ws).as_posix()
            if target_rel not in discovered:
                discovered.append(target_rel)
    except (OSError, ValueError) as exc:
        _get_logger().warning(f"Scaffolder : Skipping target crate path resolution for .cargo/config.toml: {exc}")

    existing_paths: typeList[str] = []
    existing_content = ""
    if cargo_config_path.is_file():
        try:
            existing_content = cargo_config_path.read_text(encoding="utf-8")
            paths_match = reSearch(r"(?m)^\s*paths\s*=\s*\[(.*?)\]", existing_content, flags=reDotAll)
            if paths_match:
                existing_paths = reFindall(r'["\']([^"\']+)["\']', paths_match.group(1))
        except Exception as e:
            _get_logger().warning(f"Scaffolder : Could not read .cargo/config.toml: {e}")
            return
    elif not discovered:
        return

    merged_paths: typeList[str] = []
    normalized_seen: typeSet[str] = set()
    for p in existing_paths + discovered:
        norm = p.lstrip("./")
        if norm not in normalized_seen:
            normalized_seen.add(norm)
            merged_paths.append(p)

    if cargo_config_path.is_file() and len(merged_paths) == len(existing_paths):
        return

    paths_block = "paths = [\n" + "".join(f'    "{p}",\n' for p in merged_paths) + "]"
    try:
        if cargo_config_path.is_file() and reSearch(r"(?m)^\s*paths\s*=\s*\[.*?\]", existing_content, flags=reDotAll):
            updated_content = reSub(
                r"(?m)^\s*paths\s*=\s*\[.*?\]",
                paths_block,
                existing_content,
                count=1,
                flags=reDotAll,
            )
        else:
            header = (
                "# =============================================================================\n"
                "# ESSENTIAL PROCESS: Workspace-level Cargo local dependency override configuration (Rust equivalent of go.work).\n"
                "#\n"
                "# DATA FLOW:\n"
                "#   1. Discovered automatically by Cargo when compiling any crate inside the workspace.\n"
                "#   2. Overrides remote GitHub dependencies with local sibling crate source code.\n"
                "#   3. Ignored automatically in standalone CI / Docker builds where this workspace root file is absent.\n"
                "#\n"
                "# KEY PARAMETERS:\n"
                "#   - paths: Workspace-relative paths to local Rust library crates.\n"
                "# =============================================================================\n\n"
            )
            updated_content = (existing_content.rstrip() + "\n\n" + paths_block + "\n") if existing_content.strip() else (header + paths_block + "\n")

        cargo_config_path.parent.mkdir(parents=True, exist_ok=True)
        cargo_config_path.write_text(updated_content, encoding="utf-8")
        _get_logger().info(f"Scaffolder : 🔗 Registered local Rust crates in .cargo/config.toml ({len(merged_paths)} path(s))")
    except Exception as e:
        _get_logger().warning(f"Scaffolder : Could not update .cargo/config.toml: {e}")
# -----------------------------------------------------------------------------------------------

def _is_external_domain_workspace(brain_dir: pathPath, workspace_root: pathPath) -> bool:
    """
    Returns True when brain_dir is a pure domain vault inside an external domain workspace
    container (brain_dir outside Bastien-Antigravity with brain_dir.parent/standalone.yaml
    existing as a regular non-symlink file).
    """
    parent_yaml = brain_dir.parent / "standalone.yaml"
    return (
        parent_yaml.is_file()
        and not parent_yaml.is_symlink()
        and not _is_core_workspace(brain_dir, workspace_root)
    )
# -----------------------------------------------------------------------------------------------

def _resolve_brain_name(target_dir: pathPath, brain_name: typeOptional[str] = None) -> str:
    """
    Resolves the concrete target knowledge brain directory name for ServiceSpec.DocLink
    without defaulting blindly to 'obsidian-brain' inside external domain workspaces.
    """
    if brain_name:
        return brain_name
    if target_dir.parent.name == "06-Microservices":
        return target_dir.parent.parent.name
    parent_yaml = target_dir.parent / "standalone.yaml"
    if parent_yaml.is_file() and not parent_yaml.is_symlink():
        try:
            candidates = [
                d for d in target_dir.parent.iterdir()
                if d.is_dir() and (d / "06-Microservices").is_dir() and (d / "02-Business-BDD").is_dir()
            ]
        except OSError:
            candidates = []
        if len(candidates) == 1:
            return candidates[0].name
    return "obsidian-brain"
# -----------------------------------------------------------------------------------------------

def _to_pascal_case(name: str) -> str:
    """Converts a kebab/snake identifier into PascalCase."""
    return "".join(part.capitalize() for part in name.replace("_", "-").split("-") if part)
# -----------------------------------------------------------------------------------------------

def generate_openmfe_component_js(name: str, cap_name: str, desc: str) -> str:
    """Generates a standardized BastienMFEElement Web Component with dynamic Exchange Contract tabs."""
    class_name = _to_pascal_case(name) + "MFE"
    tag_name = f"{name}-mfe"
    tabs_id = f"{cap_name}-tabs-bar"
    panels_id = f"{cap_name}-panels-host"
    return f"""// ============================================================================
// Standardized OpenMFE Web Component for {name}
// Consumes authoritative Exchange Contracts from GET /api/v1/contracts via BastienMFEContracts.
// ============================================================================

class {class_name} extends (window.BastienMFEElement || HTMLElement) {{
    render() {{
        this.innerHTML = `
            <div class="openmfe-container">
                <div class="openmfe-kpi-grid">
                    <div class="openmfe-kpi-card">
                        <span class="openmfe-kpi-label"><i class="fa fa-heartbeat"></i> Status</span>
                        <span class="openmfe-kpi-val" id="{cap_name}-kpi-status">Checking...</span>
                        <span class="openmfe-kpi-sub">{desc}</span>
                    </div>
                    <div class="openmfe-kpi-card">
                        <span class="openmfe-kpi-label"><i class="fa fa-tag"></i> Version</span>
                        <span class="openmfe-kpi-val" id="{cap_name}-kpi-version">—</span>
                        <span class="openmfe-kpi-sub">VERSION.txt</span>
                    </div>
                    <div class="openmfe-kpi-card">
                        <span class="openmfe-kpi-label"><i class="fa fa-exchange"></i> Exchange Contracts</span>
                        <span class="openmfe-kpi-val" id="{cap_name}-kpi-contracts">—</span>
                        <span class="openmfe-kpi-sub">Authoritative Service Introspection</span>
                    </div>
                </div>

                <div class="openmfe-tabs-bar" id="{tabs_id}" role="tablist">
                    <button type="button" class="openmfe-tab-btn is-active" data-tab="overview" role="tab">
                        <i class="fa fa-tachometer"></i> Live Overview
                    </button>
                </div>

                <div id="{panels_id}">
                    <div class="openmfe-panel is-active" id="panel-overview">
                        <div class="openmfe-card">
                            <div class="openmfe-card__header">
                                <h4 class="openmfe-card__title"><i class="fa fa-sliders"></i> {name} Live Operations</h4>
                                <button type="button" class="openmfe-btn openmfe-btn--sm" id="{cap_name}-btn-refresh">
                                    <i class="fa fa-refresh"></i> Refresh
                                </button>
                            </div>
                            <div class="openmfe-card__body" id="{cap_name}-overview-body">
                                <p class="openmfe-text-muted"><i class="fa fa-spinner fa-spin"></i> Loading service telemetry...</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }}

    cacheDom() {{
        this.activeTab = this.activeTab || 'overview';
        this.dom = {{
            kpiStatus: this.querySelector('#{cap_name}-kpi-status'),
            kpiVersion: this.querySelector('#{cap_name}-kpi-version'),
            kpiContracts: this.querySelector('#{cap_name}-kpi-contracts'),
            tabsBar: this.querySelector('#{tabs_id}'),
            panelsHost: this.querySelector('#{panels_id}'),
            overviewBody: this.querySelector('#{cap_name}-overview-body'),
            btnRefresh: this.querySelector('#{cap_name}-btn-refresh')
        }};
    }}

    bindEvents() {{
        if (this.dom.btnRefresh) {{
            this.dom.btnRefresh.addEventListener('click', () => {{
                this.fetchHealth();
                this.loadContracts();
            }});
        }}
        if (this.dom.tabsBar) {{
            this.dom.tabsBar.querySelectorAll('.openmfe-tab-btn').forEach(btn => {{
                btn.addEventListener('click', () => this.switchTab(btn.getAttribute('data-tab') || 'overview'));
            }});
        }}
    }}

    switchTab(tabId) {{
        this.activeTab = tabId;
        if (!this.dom.tabsBar || !this.dom.panelsHost) return;
        this.dom.tabsBar.querySelectorAll('.openmfe-tab-btn').forEach(btn => {{
            btn.classList.toggle('is-active', btn.getAttribute('data-tab') === tabId);
        }});
        this.dom.panelsHost.querySelectorAll('.openmfe-panel').forEach(panel => {{
            panel.classList.toggle('is-active', panel.id === `panel-${{tabId}}`);
        }});
    }}

    onMount() {{
        this.fetchHealth();
        this.loadContracts();
        this.registerPoll(() => this.fetchHealth(), 5000);
    }}

    async fetchHealth() {{
        try {{
            const data = await this.apiFetch('/api/v1/health');
            if (this.dom.kpiStatus) this.dom.kpiStatus.textContent = (data && data.status) || 'Healthy';
            if (this.dom.kpiVersion && data && data.version) this.dom.kpiVersion.textContent = `v${{data.version}}`;
            if (this.dom.overviewBody) {{
                this.dom.overviewBody.innerHTML = `<pre class="openmfe-code-preview">${{JSON.stringify(data, null, 2)}}</pre>`;
            }}
        }} catch (err) {{
            if (this.dom.kpiStatus) this.dom.kpiStatus.textContent = 'Offline';
            if (this.showError && this.dom.overviewBody) {{
                this.showError(this.dom.overviewBody, `Health check failed: ${{err.message}}`, () => this.fetchHealth());
            }}
        }}
    }}

    async loadContracts() {{
        const helper = window.BastienMFEContracts;
        if (!helper || !this.dom.tabsBar || !this.dom.panelsHost) return;
        const envelope = await helper.fetchContracts({{
            primaryUrls: [this.apiUrl('/api/v1/contracts')],
            serviceName: '{cap_name}'
        }});
        if (this.dom.kpiContracts) {{
            const count = Array.isArray(envelope.contracts) ? envelope.contracts.length : 0;
            this.dom.kpiContracts.textContent = envelope.reliable ? `${{count}} contract(s)` : 'Unavailable';
        }}
        helper.mountContractTabs({{
            rootEl: this,
            tabsBarEl: this.dom.tabsBar,
            panelsHostEl: this.dom.panelsHost,
            envelope,
            activeTab: this.activeTab,
            onSwitchTab: (tab) => this.switchTab(tab),
            onRetry: () => this.loadContracts()
        }});
    }}
}}

if (window.BastienMFEElement && typeof window.BastienMFEElement.register === 'function') {{
    window.BastienMFEElement.register('{tag_name}', {class_name});
}} else if (typeof customElements !== 'undefined' && !customElements.get('{tag_name}')) {{
    customElements.define('{tag_name}', {class_name});
}}
"""
# -----------------------------------------------------------------------------------------------

def generate_common_files(
    target_dir: pathPath,
    name: str,
    lang: str,
    port: int,
    desc: str,
    dry_run: bool,
    layer: str = "L3",
    fleet_mode: str = "local"
) -> None:
    """Generates files mandatory across all languages: Dockerfile, compose, AGENTS.md, etc."""
    cap_name = name.replace("-", "_")
    workspace_root = resolve_workspace_root()

    # Resolve standalone.yaml symlink target dynamically so external L3/L4/L5 repos never get dangling links
    brain_root_candidate = target_dir.parent.parent if target_dir.parent.name == "06-Microservices" else None
    parent_standalone = target_dir.parent / "standalone.yaml"
    if brain_root_candidate and (
        (brain_root_candidate / "standalone.yaml").exists()
        or (brain_root_candidate / "standalone.yaml").is_symlink()
    ):
        standalone_link_target = "../../standalone.yaml"
    elif (
        parent_standalone.is_file()
        and not parent_standalone.is_symlink()
        and not _is_core_workspace(target_dir, workspace_root)
    ):
        standalone_link_target = "../standalone.yaml"
    else:
        if fleet_mode == "docker":
            cfg_rel_parts = ("docker-deployment", "modes", "docker", "config", "host-bridge.yaml")
            fallback_rel_target = "../docker-deployment/modes/docker/config/host-bridge.yaml"
        else:
            cfg_rel_parts = ("docker-deployment", "modes", "local", "config", "native.yaml")
            fallback_rel_target = "../docker-deployment/modes/local/config/native.yaml"
        fleet_cfg_candidates = [
            workspace_root.joinpath(*cfg_rel_parts),
            target_dir.parent.joinpath(*cfg_rel_parts),
        ]
        fleet_cfg = next((c for c in fleet_cfg_candidates if c.is_file()), None)
        if fleet_cfg is not None:
            try:
                standalone_link_target = osPathRelpath(str(fleet_cfg), str(target_dir.resolve()))
            except ValueError:
                standalone_link_target = str(fleet_cfg.resolve())
        else:
            standalone_link_target = fallback_rel_target

    # 1. Dockerfile (Multi-stage compliant with 12-Docker-Deployment-Standards.md)
    if lang == "go":
        dockerfile = f"""# === BUILD STAGE ===
FROM golang:1.25-alpine AS builder

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"

RUN apk add --no-cache git gcc musl-dev ca-certificates tzdata

WORKDIR /workspace

# Clone shared library modules for go.work resolution in builder stage
RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git /workspace/microservice-toolbox && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/distributed-config.git /workspace/distributed-config && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/safe-socket.git /workspace/safe-socket && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/universal-logger.git /workspace/universal-logger && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/flexible-logger.git /workspace/flexible-logger

# Copy service source
WORKDIR /workspace/{name}
COPY . .

# Initialize go.work across cloned /workspace modules and build binary
RUN go work init /workspace/{name} /workspace/microservice-toolbox /workspace/distributed-config /workspace/safe-socket /workspace/universal-logger /workspace/flexible-logger && \\
    VERSION=$(cat VERSION.txt) && \\
    CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w -X 'github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/version.BuildVersion=${{VERSION}}'" -o /{name}-bin ./cmd/{name}

# === RUNTIME STAGE ===
FROM alpine:3.20

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /{name}

COPY --from=builder /{name}-bin /{name}/{name}
COPY --from=builder /workspace/{name}/VERSION.txt ./VERSION.txt

ENTRYPOINT ["/{name}/{name}"]
"""
    elif lang == "rust":
        dockerfile = f"""# === BUILD STAGE ===
FROM rust:1.91-alpine AS builder

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"

RUN apk add --no-cache musl-dev gcc git

WORKDIR /workspace/{name}
COPY . .

RUN cargo build --release

# === RUNTIME STAGE ===
FROM alpine:3.20

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /{name}

COPY --from=builder /workspace/{name}/target/release/{name} /{name}/{name}
COPY --from=builder /workspace/{name}/VERSION.txt ./VERSION.txt

ENTRYPOINT ["/{name}/{name}"]
"""
    elif lang == "cpp":
        dockerfile = f"""# === BUILD STAGE (Compile CGO shared libraries + C++ binary) ===
FROM golang:1.25-alpine AS go-builder

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"

WORKDIR /workspace
RUN apk add --no-cache git gcc musl-dev libc-dev
RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git /workspace/microservice-toolbox && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/distributed-config.git /workspace/distributed-config && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/safe-socket.git /workspace/safe-socket && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/universal-logger.git /workspace/universal-logger && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/flexible-logger.git /workspace/flexible-logger && \\
    go work init /workspace/microservice-toolbox /workspace/distributed-config /workspace/safe-socket /workspace/universal-logger /workspace/flexible-logger && \\
    cd /workspace/distributed-config && go build -buildmode=c-shared -o /workspace/libdistconf.so ./cmd/libdistconf && \\
    cd /workspace/universal-logger && go build -buildmode=c-shared -o /workspace/libunilog.so ./src/cgo_bridge

FROM alpine:3.20 AS cpp-builder
RUN apk add --no-cache g++ make
WORKDIR /workspace
COPY --from=go-builder /workspace/microservice-toolbox /workspace/microservice-toolbox
COPY --from=go-builder /workspace/libdistconf.so /usr/local/lib/libdistconf.so
COPY --from=go-builder /workspace/distributed-config/distconf/libdistconf /workspace/distributed-config/distconf/libdistconf
WORKDIR /workspace/{name}
COPY . .
RUN VERSION=$(cat VERSION.txt) && \\
    g++ -std=c++17 -O2 -Wall -Wextra -DAPP_VERSION=\\"${{VERSION}}\\" -Isrc -I/workspace/microservice-toolbox/cpp/include -I/workspace/distributed-config/distconf/libdistconf src/main.cpp -o /{name}-bin -L/usr/local/lib -ldistconf

# === RUNTIME STAGE ===
FROM alpine:3.20
LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"
RUN apk add --no-cache ca-certificates tzdata libstdc++
WORKDIR /{name}
COPY --from=go-builder /workspace/libdistconf.so /usr/local/lib/libdistconf.so
COPY --from=go-builder /workspace/libunilog.so /usr/local/lib/libunilog.so
COPY --from=cpp-builder /{name}-bin /{name}/{name}
COPY --from=cpp-builder /workspace/{name}/VERSION.txt ./VERSION.txt
ENTRYPOINT ["/{name}/{name}"]
"""
    else:
        dockerfile = f"""# === BUILD STAGE (Compile CGO libunilog.so) ===
FROM golang:1.25-alpine AS go-builder

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"

WORKDIR /workspace

RUN apk add --no-cache git gcc musl-dev libc-dev

RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git /workspace/microservice-toolbox && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/distributed-config.git /workspace/distributed-config && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/safe-socket.git /workspace/safe-socket && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/universal-logger.git /workspace/universal-logger && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/flexible-logger.git /workspace/flexible-logger && \\
    go work init /workspace/microservice-toolbox /workspace/distributed-config /workspace/safe-socket /workspace/universal-logger /workspace/flexible-logger && \\
    cd /workspace/universal-logger && \\
    go build -buildmode=c-shared -o /workspace/libunilog.so ./src/cgo_bridge

# === PYTHON RUNTIME STAGE ===
FROM python:3.12-alpine

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"

RUN apk add --no-cache ca-certificates tzdata git build-base

WORKDIR /{name}

# Install compiled libunilog.so system-wide
COPY --from=go-builder /workspace/libunilog.so /usr/local/lib/libunilog.so

# Clone & install microservice-toolbox python package
RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git /tmp/microservice-toolbox && \\
    pip install --no-cache-dir /tmp/microservice-toolbox/python && \\
    rm -rf /tmp/microservice-toolbox

# Install service dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY . .

ENTRYPOINT ["python3", "main.py"]
"""
    create_file(target_dir / "Dockerfile", dockerfile, dry_run)

    # 2. docker-compose.yml (Local fragment)
    compose_yml = f"""services:
  {name}:
    build:
      context: .
      dockerfile: Dockerfile
    image: ghcr.io/bastien-antigravity/{name}:${{TAG:-latest}}
    container_name: {name}
    restart: unless-stopped
    ports:
      - "${{HOST_IP:-127.0.0.1}}:{port}:{port}"
    volumes:
      - ./standalone.yaml:/{name}/standalone.yaml:ro
    networks:
      - teleremote-network

networks:
  teleremote-network:
    name: teleremote-network
    external: true
"""
    create_file(target_dir / "docker-compose.yml", compose_yml, dry_run)

    # 3. AGENTS.md
    if lang == "go":
        test_cmd = "go test -v ./..."
        build_cmd = f"go build -o bin/{name} ./cmd/{name}"
        run_cmd = f"./bin/{name}"
    elif lang == "python":
        test_cmd = "pytest"
        build_cmd = "pip install -r requirements.txt"
        run_cmd = "python3 main.py"
    elif lang == "cpp":
        test_cmd = "make test"
        build_cmd = "make build"
        run_cmd = f"./bin/{name}"
    else:
        test_cmd = "cargo test"
        build_cmd = "cargo build"
        run_cmd = f"./target/debug/{name}"

    agents_md = f"""# AGENTS.md: {name}

## Service Mission & Architecture Role
`{name}` is responsible for: {desc}.

- **Exposed Capability**: `{cap_name}` (Port: `{port}`)
- **Architecture Layer**: `{layer}`
- **Shared Libraries**: `microservice-toolbox`, `universal-logger`, `distributed-config`, `safe-socket`
- **Configuration Link**: `standalone.yaml -> {standalone_link_target}`

## Key Build & Test Commands
```bash
# Build binary
{build_cmd}

# Run tests
{test_cmd}

# Run service locally
{run_cmd}
```

## AI Development & Integration Guidelines
1. **Bootstrap Ritual & Cold-Path Fail-Fast Validation**: Initialized using `toolbox_bootstrap.BootstrapService("{name}")` (Go), `load_config` / `bootstrap_microservice` (Python/Rust), or `LoadConfig` (C++). Validate configuration and `VERSION.txt` once at boot and fail fast on missing requirements; downstream hot paths MUST trust pre-validated `AppConfig` string values without redundant re-checks or locks (checking optionality only for genuinely optional parameters).
2. **Dynamic Port Resolution & Zero Silent Fallback**: Always use `appConfig.GetListenAddr("{cap_name}")` / `GetCapability("{cap_name}", &cap)`. NEVER hardcode IPs (`127.0.0.1`, `0.0.0.0`), port numbers, or `"0.0.1"` fallbacks. (`VERSION.txt` is the sole version source; zero runtime `APP_VERSION`/`SERVICE_VERSION` overrides.)
3. **Encrypted Secrets**: Sensitive values stored in configurations must remain encrypted as `ENC(...)` tokens until runtime decryption via `appConfig.DecryptSecret()`.
4. **Canonical Log Levels (`flexible-logger`)**: Use only the 12 canonical levels from `flexible-logger/src/models/level.go` (`NOTSET=0`, `DEBUG=1`, `STREAM=2`, `INFO=3`, `LOGON=4`, `LOGOUT=5`, `TRADE=6`, `SCHEDULE=7`, `REPORT=8`, `WARNING=9`, `ERROR=10`, `CRITICAL=11`); only `ERROR`/`CRITICAL` persist to TimescaleDB via `watchdog-agent`.
5. **Header Ritual**: All source files MUST begin with the standard Triple-Block header (`ESSENTIAL PROCESS`, `DATA FLOW`, `KEY PARAMETERS`).
6. **Section Dividers**: Use appropriate dividers (`// -----------------------------------------------------------------------------`) between exported methods and major sections.
7. **Dynamic Fleet Hot-Reloading**: Microservices must register `OnLiveConfUpdate` / `on_live_conf_update` to dynamically reload configuration changes without restarting the daemon process.
8. **Service Specification, OpenMFE & Authoritative Exchange Contracts Standard**:
   - Register declarative `ServiceSpec` + `Contracts` (`ExchangeContract[]`) during bootstrap using `spec.PublishWithLifecycle` (Go), `spec.publish_with_lifecycle` (Python), `spec::publish_with_lifecycle` (Rust), or `SpecPublisher::PublishWithLifecycle` (C++, with `contracts.hpp` / `contracts.h` for C ABI) with infinite resilience (`MaxRetries: -1`) and non-blocking execution.
   - HTTP services MUST expose `GET /api/v1/contracts` (`ContractsEnvelope`) built from live runtime routes and embedded schemas, and OpenMFE components (`mfe.js`) MUST use `BastienMFEElement` + `window.BastienMFEContracts` inside `.openmfe-tabs-bar` (`div[3]`) without fabricating mock schemas or using brittle `?v=` CSS query strings.
9. **Real-Time Transport WireTap & Dynamic Topology (`> L3` Ready)**: `BootstrapService` (Go) and `init_microservice` / `configure_from_config` (Python) automatically bind the lock-free WireTap transport telemetry engine (`microservice-toolbox/go/pkg/wiretap`, `microservice_toolbox/wiretap.py`) to `safe-socket`, gRPC (`teleremote`, `notification`, `network`), and NATS (`messaging`). Combined with `spec.PublishWithLifecycle`, this microservice (`L2`, `L3`, or `> L3` / `L4+`) and its live edges and segregated channels are synthesized automatically on `web-interface` (`src/router/mesh_topology.go`) with zero hardcoded topology changes in `web-interface`.
"""
    create_file(target_dir / "AGENTS.md", agents_md, dry_run)

    # 4. AI-Init.md
    init_md = f"""---
microservice: {name}
type: governance
status: active
---

# ⚡ AI Initialization: {name}

> [!IMPORTANT] MANDATORY INITIALIZATION
> Copy and paste this prompt when starting a new session in this repository:
> 
> "1. Read the ecosystem map in **[[Ecosystem-Map-MOC]]**."
> "2. Load project constraints from **[[AI-Project-DNA]]**."
> "3. Restore session state from **[[AI-Session-State]]**."
> "4. **Sentinel Audit**: Run `python3 08-Squad-Agent/main.py preflight-check` and resolve any drift."
> "5. **Squad Protocol**: You are now the **Lead Developer**. Identify and hire the required **Specialists** from `07-Core-KMS/Role-Prompts/03-Developer/Squad/`."
"""
    create_file(target_dir / "AI-Init.md", init_md, dry_run)

    # 5. AI-Project-DNA.md
    dna_md = f"""# Metadata
- Version: 0.0.1
- Classification: {layer} Microservice

---
microservice: {name}
type: note
status: active
tags:
- '#service/{name}'
- '#type/note'
- '#state/active'
- '#tier/{layer.lower()}'
- '#zone/3-fleet'
---

# 🧬 Project DNA: {name}

## 🎯 High-Level Intent (BDD)
- **Goal**: {desc}
- **Behavioral Source of Truth**: [[02-Business-BDD/02-Behavior-Specs/{name}/FEAT-001-Initialization.md]]

## 🛠️ Role Specifics
- **Architect**: Ensure sovereign configuration resolution via microservice-toolbox and adherence to ecosystem networking.
- **QA**: Validate unit test coverage and integration scenarios in sandbox-testing.
- **Developer**: Fulfill the capability contract defined in AGENTS.md.

## 🚦 Lifecycle & Versioning
- **Primary Branch**: `develop`
- **Protected Branches**: `main`, `master`
- **Versioning Strategy**: Semantic Versioning (v0.0.1).
- **Version Source of Truth**: `VERSION.txt`.
"""
    create_file(target_dir / "AI-Project-DNA.md", dna_md, dry_run)

    # 6. AI-Session-State.md
    session_md = f"""---
microservice: {name}
type: session-state
status: active
tags:
  - '#service/{name}'
  - '#type/session-state'
  - '#state/active'
  - '#zone/3-fleet'
---

# AI Session State: {name}

Mission-ID: MISSION-SCAFFOLD-001
Status: Initialized / Ready
"""
    create_file(target_dir / "AI-Session-State.md", session_md, dry_run)

    # 7. TODO.md
    todo_md = f"""# TODO: {name}

- [ ] Implement core business logic controllers
- [ ] Connect inter-service dependencies via microservice-toolbox
- [ ] Implement end-to-end integration tests in sandbox-testing
"""
    create_file(target_dir / "TODO.md", todo_md, dry_run)

    # 8. README.md
    readme_md = f"""# {name}

{desc}

## Architecture & Integration
See [AGENTS.md](AGENTS.md) for technical specifications, capability ports, and AI development rules.
"""
    create_file(target_dir / "README.md", readme_md, dry_run)

    # 6. VERSION.txt
    create_file(target_dir / "VERSION.txt", "0.0.1\n", dry_run)

    # 7. Makefile (Dynamic Versioning Standard - Go, Rust, C++ compiled projects)
    if lang == "go":
        makefile = f"""VERSION ?= $(shell cat VERSION.txt)
export GOPRIVATE=github.com/Bastien-Antigravity/*
LDFLAGS := -s -w -X 'github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/version.BuildVersion=$(VERSION)'

.PHONY: all build test race vet version clean run

all: build

version:
\t@echo $(VERSION)

build:
\t@echo "Building {name} (version $(VERSION))..."
\t@mkdir -p bin
\tgo build -ldflags="$(LDFLAGS)" -o bin/{name} ./cmd/{name}

test:
\t@echo "Running tests for {name} (version $(VERSION))..."
\tgo test -v ./...

race:
\t@echo "Running race detector (version $(VERSION))..."
\tgo test -race -v ./...

vet:
\t@echo "Running go vet..."
\tgo vet ./...

run:
\t./bin/{name}

clean:
\t@echo "Cleaning build artifacts..."
\t@rm -rf bin/ dist/ build/
"""
        create_file(target_dir / "Makefile", makefile, dry_run)
    elif lang == "rust":
        makefile = f"""VERSION ?= $(shell cat VERSION.txt)

.PHONY: all build test version clean run

all: build

version:
\t@echo $(VERSION)

build:
\t@echo "Building {name} (version $(VERSION))..."
\tcargo build --release

test:
\t@echo "Running tests for {name} (version $(VERSION))..."
\tcargo test

run:
\tcargo run

clean:
\t@echo "Cleaning build artifacts..."
\tcargo clean
"""
        create_file(target_dir / "Makefile", makefile, dry_run)
    elif lang == "cpp":
        is_core_cpp = _is_core_workspace(target_dir, workspace_root)
        core_rel_candidates = ""
        if is_core_cpp:
            core_rel_candidates = """list(APPEND _BASTIEN_TOOLBOX_CANDIDATES
    "${CMAKE_CURRENT_SOURCE_DIR}/../microservice-toolbox/cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../microservice-toolbox/cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../microservice-toolbox/cpp"
)
"""
        cmake_lists = f"""cmake_minimum_required(VERSION 3.20)

file(STRINGS "${{CMAKE_CURRENT_SOURCE_DIR}}/VERSION.txt" APP_VERSION LIMIT_COUNT 1)
string(STRIP "${{APP_VERSION}}" APP_VERSION)

project({name} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# -----------------------------------------------------------------------------
# Local-First Workspace Resolution with GitHub FetchContent Fallback
# -----------------------------------------------------------------------------
set(_BASTIEN_TOOLBOX_CANDIDATES)
if(DEFINED ENV{{BASTIEN_CORE_ROOT}} AND NOT "$ENV{{BASTIEN_CORE_ROOT}}" STREQUAL "")
    list(APPEND _BASTIEN_TOOLBOX_CANDIDATES "$ENV{{BASTIEN_CORE_ROOT}}/microservice-toolbox/cpp")
endif()
if(DEFINED ENV{{BASTIEN_WORKSPACE_ROOT}} AND NOT "$ENV{{BASTIEN_WORKSPACE_ROOT}}" STREQUAL "")
    list(APPEND _BASTIEN_TOOLBOX_CANDIDATES "$ENV{{BASTIEN_WORKSPACE_ROOT}}/microservice-toolbox/cpp")
endif()
{core_rel_candidates}set(_CANDIDATE_TOOLBOX_CPP "")
foreach(_cand IN LISTS _BASTIEN_TOOLBOX_CANDIDATES)
    if(EXISTS "${{_cand}}/CMakeLists.txt")
        get_filename_component(_CANDIDATE_TOOLBOX_CPP "${{_cand}}" ABSOLUTE)
        break()
    endif()
endforeach()

set(_WORKSPACE_ROOT "")
set(_LOCAL_DISTCONF_HINTS)
if(EXISTS "${{_CANDIDATE_TOOLBOX_CPP}}/CMakeLists.txt")
    set(FETCHCONTENT_SOURCE_DIR_MICROSERVICE_TOOLBOX "${{_CANDIDATE_TOOLBOX_CPP}}" CACHE PATH "Local workspace microservice-toolbox/cpp override" FORCE)
    get_filename_component(_TOOLBOX_REPO_DIR "${{_CANDIDATE_TOOLBOX_CPP}}" DIRECTORY)
    get_filename_component(_WORKSPACE_ROOT "${{_TOOLBOX_REPO_DIR}}" DIRECTORY)
    list(APPEND _LOCAL_DISTCONF_HINTS
        "${{_WORKSPACE_ROOT}}/distributed-config/distconf/libdistconf"
        "${{_WORKSPACE_ROOT}}/universal-logger/libunilog"
        "${{_WORKSPACE_ROOT}}/notif-server/notif/libnotif"
    )
    message(STATUS "{name}: using local workspace microservice-toolbox at ${{_CANDIDATE_TOOLBOX_CPP}}")
endif()

# Auto-discover sibling custom *-toolbox/cpp/CMakeLists.txt in local workspace(s)
get_filename_component(_PARENT_WS_DIR "${{CMAKE_CURRENT_SOURCE_DIR}}/.." ABSOLUTE)
set(_TOOLBOX_SCAN_ROOTS "${{_PARENT_WS_DIR}}")
if(_WORKSPACE_ROOT)
    list(APPEND _TOOLBOX_SCAN_ROOTS "${{_WORKSPACE_ROOT}}")
endif()
if(DEFINED ENV{{BASTIEN_WORKSPACE_ROOT}} AND NOT "$ENV{{BASTIEN_WORKSPACE_ROOT}}" STREQUAL "")
    list(APPEND _TOOLBOX_SCAN_ROOTS "$ENV{{BASTIEN_WORKSPACE_ROOT}}")
endif()
list(REMOVE_DUPLICATES _TOOLBOX_SCAN_ROOTS)

foreach(_scan_root IN LISTS _TOOLBOX_SCAN_ROOTS)
    file(GLOB _SIBLING_TOOLBOXES LIST_DIRECTORIES true "${{_scan_root}}/*-toolbox/cpp")
    foreach(_tb_cpp IN LISTS _SIBLING_TOOLBOXES)
        if(EXISTS "${{_tb_cpp}}/CMakeLists.txt")
            get_filename_component(_tb_repo "${{_tb_cpp}}" DIRECTORY)
            get_filename_component(_tb_name "${{_tb_repo}}" NAME)
            string(TOUPPER "${{_tb_name}}" _tb_upper)
            string(REPLACE "-" "_" _tb_upper "${{_tb_upper}}")
            if(NOT DEFINED FETCHCONTENT_SOURCE_DIR_${{_tb_upper}})
                set(FETCHCONTENT_SOURCE_DIR_${{_tb_upper}} "${{_tb_cpp}}" CACHE PATH "Local workspace ${{_tb_name}}/cpp override" FORCE)
            endif()
        endif()
    endforeach()
endforeach()

include(FetchContent)
FetchContent_Declare(
    microservice_toolbox
    GIT_REPOSITORY https://github.com/Bastien-Antigravity/microservice-toolbox.git
    GIT_TAG        develop
    SOURCE_SUBDIR  cpp
)
FetchContent_MakeAvailable(microservice_toolbox)

find_library(DISTCONF_LIB
    NAMES distconf
    HINTS
        "${{LIBDISTCONF_PATH}}"
        "$ENV{{LIBDISTCONF_PATH}}"
        ${{_LOCAL_DISTCONF_HINTS}}
        "$ENV{{HOME}}/.bastien/lib"
        "/usr/local/lib"
)
find_path(DISTCONF_INCLUDE_DIR
    NAMES libdistconf.h
    HINTS
        "${{LIBDISTCONF_PATH}}"
        "$ENV{{LIBDISTCONF_PATH}}"
        ${{_LOCAL_DISTCONF_HINTS}}
        "$ENV{{HOME}}/.bastien/include"
        "$ENV{{HOME}}/.bastien/lib"
        "/usr/local/include"
)
if(NOT DISTCONF_LIB)
    message(FATAL_ERROR "libdistconf not found. Set -DLIBDISTCONF_PATH=... or install to ~/.bastien/lib or /usr/local/lib")
endif()

get_filename_component(DISTCONF_LIB_DIR "${{DISTCONF_LIB}}" DIRECTORY)

add_executable({name} src/main.cpp)
target_include_directories({name} PRIVATE src)
if(DISTCONF_INCLUDE_DIR)
    target_include_directories({name} PRIVATE "${{DISTCONF_INCLUDE_DIR}}")
endif()
target_compile_definitions({name} PRIVATE APP_VERSION="${{APP_VERSION}}")
target_link_libraries({name} PRIVATE microservice_toolbox::toolbox "${{DISTCONF_LIB}}")
set_target_properties({name} PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${{CMAKE_CURRENT_SOURCE_DIR}}/bin"
    BUILD_RPATH "${{DISTCONF_LIB_DIR}}"
    INSTALL_RPATH "${{DISTCONF_LIB_DIR}}"
)

enable_testing()
add_executable(test_basic tests/test_basic.cpp)
target_include_directories(test_basic PRIVATE src)
if(DISTCONF_INCLUDE_DIR)
    target_include_directories(test_basic PRIVATE "${{DISTCONF_INCLUDE_DIR}}")
endif()
target_compile_definitions(test_basic PRIVATE APP_VERSION="${{APP_VERSION}}")
target_link_libraries(test_basic PRIVATE microservice_toolbox::toolbox "${{DISTCONF_LIB}}")
set_target_properties(test_basic PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${{CMAKE_CURRENT_SOURCE_DIR}}/bin"
    BUILD_RPATH "${{DISTCONF_LIB_DIR}}"
    INSTALL_RPATH "${{DISTCONF_LIB_DIR}}"
)
add_test(NAME test_basic COMMAND test_basic)
"""
        create_file(target_dir / "CMakeLists.txt", cmake_lists, dry_run)

        if _is_core_workspace(target_dir, workspace_root):
            try:
                cpp_ws_rel = osPathRelpath(str(workspace_root.resolve()), str(target_dir.resolve()))
            except ValueError:
                cpp_ws_rel = ".."
            makefile = f"""VERSION ?= $(shell cat VERSION.txt)
CXX ?= g++
DISTCONF_DIR ?= {cpp_ws_rel}/distributed-config/distconf/libdistconf
TOOLBOX_CPP_INC ?= {cpp_ws_rel}/microservice-toolbox/cpp/include
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Isrc -I$(TOOLBOX_CPP_INC) -I$(DISTCONF_DIR) -DAPP_VERSION=\\"$(VERSION)\\"
LDFLAGS ?= -L$(DISTCONF_DIR) -ldistconf -Wl,-rpath,$(DISTCONF_DIR)

.PHONY: all build test version clean run

all: build

version:
\t@echo $(VERSION)

build:
\t@echo "Building {name} (version $(VERSION))..."
\t@mkdir -p bin
\t$(CXX) $(CXXFLAGS) src/main.cpp -o bin/{name} $(LDFLAGS)

test:
\t@echo "Running C++ tests for {name} (version $(VERSION))..."
\t@mkdir -p bin
\t$(CXX) $(CXXFLAGS) tests/test_basic.cpp -o bin/test_basic $(LDFLAGS)
\tDYLD_LIBRARY_PATH="$(DISTCONF_DIR):$$DYLD_LIBRARY_PATH" LD_LIBRARY_PATH="$(DISTCONF_DIR):$$LD_LIBRARY_PATH" ./bin/test_basic

run:
\tDYLD_LIBRARY_PATH="$(DISTCONF_DIR):$$DYLD_LIBRARY_PATH" ./bin/{name}

clean:
\t@echo "Cleaning build artifacts..."
\t@rm -rf bin/ build/
"""
        else:
            makefile = f"""VERSION ?= $(shell cat VERSION.txt)
CXX ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra
BUILD_DIR ?= build
LIBDISTCONF_PATH ?=

.PHONY: all configure build test version clean run

all: build

version:
\t@echo $(VERSION)

configure:
\tcmake -S . -B $(BUILD_DIR) -DCMAKE_CXX_COMPILER="$(CXX)" -DCMAKE_CXX_FLAGS="$(CXXFLAGS)" -DLIBDISTCONF_PATH="$(LIBDISTCONF_PATH)"

build: configure
\t@echo "Building {name} (version $(VERSION))..."
\tcmake --build $(BUILD_DIR) --target {name}

test: configure
\t@echo "Running C++ tests for {name} (version $(VERSION))..."
\tcmake --build $(BUILD_DIR) --target test_basic
\tctest --test-dir $(BUILD_DIR) --output-on-failure

run:
\t./bin/{name}

clean:
\t@echo "Cleaning build artifacts..."
\t@rm -rf bin/ $(BUILD_DIR)/
"""
        create_file(target_dir / "Makefile", makefile, dry_run)

    # 7. quick-overview/ human onboarding
    qo_dir = target_dir / "quick-overview"
    create_file(qo_dir / "Architecture-Overview.md", f"# Architecture Overview: {name}\n\nHigh-level component overview for human readers.\n", dry_run)
    create_file(qo_dir / "Features-Behavior.md", f"# Features & Behavior: {name}\n\nKey features and behavioral specifications for human readers.\n", dry_run)
    create_file(qo_dir / "Testing-Playbook.md", f"# Testing Playbook: {name}\n\nTesting procedures for human developers.\n", dry_run)
    create_file(qo_dir / "General-Misc.md", f"# General & Miscellaneous: {name}\n\nOperational guidelines and tips.\n", dry_run)
    create_file(qo_dir / ".geminiignore", "*\n", dry_run)
    create_file(qo_dir / ".mcpignore", "*\n", dry_run)
    create_file(qo_dir / ".aiignore", "*\n", dry_run)

    # 8. standalone.yaml symlink
    create_symlink(target_dir / "standalone.yaml", standalone_link_target, dry_run)

    # 9. .github CI/CD Workflows and Dependabot (from 05-Fleet-Operation/04-Templates)
    templates_dir = workspace_root / "obsidian-brain" / "05-Fleet-Operation" / "04-Templates"

    ci_template_path = templates_dir / "Microservice" / "ci.yml"
    try:
        ci_content = ci_template_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        ci_content = """# [FLEET-ARCHITECT] Continuous Integration
# Sync-ID: 2026-11-23-GLOBAL-001
name: Fleet CI
on:
  push:
    branches: [ develop ]
  pull_request:
    branches: [ develop ]

jobs:
  fleet-ci:
    uses: Bastien-Antigravity/fleet-operation-brain/.github/workflows/master-ci.yml@develop
    secrets: inherit
"""
    create_file(target_dir / ".github" / "workflows" / "ci.yml", ci_content, dry_run)

    docker_pub_template_path = templates_dir / "Microservice" / "docker-publish.yml"
    try:
        docker_pub_content = docker_pub_template_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        docker_pub_content = """# [FLEET-ARCHITECT] Centralized GHCR Container Image Build & Publish
# Sync-ID: 2026-11-23-GHCR-001
name: Publish Docker Image

on:
  workflow_run:
    workflows: ["Fleet CI"]
    types: [completed]
    branches: [develop]
  workflow_dispatch:

jobs:
  docker-publish:
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    uses: Bastien-Antigravity/fleet-operation-brain/.github/workflows/master-docker-publish.yml@develop
    secrets: inherit
"""
    create_file(target_dir / ".github" / "workflows" / "docker-publish.yml", docker_pub_content, dry_run)

    dep_template_path = templates_dir / "Microservice" / "dependabot.yml"
    try:
        dep_content = dep_template_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        dep_content = """version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "monthly"
"""
    create_file(target_dir / ".github" / "dependabot.yml", dep_content, dry_run)

    # 10. .gitignore
    gitignore_template = templates_dir / "gitignore-global"
    try:
        gi_content = gitignore_template.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        gi_content = """# System Files
.DS_Store
*.log
__pycache__/
*.pyc
.venv/
target/
bin/
dist/
"""
    create_file(target_dir / ".gitignore", gi_content, dry_run)
# -----------------------------------------------------------------------------------------------

def generate_bdd_spec(brain_dir: pathPath, name: str, desc: str, dry_run: bool) -> None:
    """Generates the initial BDD behavior specification note in 02-Business-BDD and service spec in 06-Microservices."""
    bdd_dir = brain_dir / "02-Business-BDD" / "02-Behavior-Specs" / name
    feat_file = bdd_dir / "FEAT-001-Initialization.md"

    content = f"""---
microservice: {name}
type: note
status: active
tags:
- '#service/{name}'
- '#type/note'
- '#state/active'
- '#zone/3-fleet'
---
# FEAT-001: Initialization & Lifecycle Management

*Back-link: [[{name}/README|⬅️ {name}]]*
---

# Feature: Service Bootstrap & Health Supervision

## 🎯 Business Intent
- **User Story**: As a platform operator, I want `{name}` to bootstrap reliably using microservice-toolbox and report health status so that the fleet orchestrator and watchdog-agent can supervise it.
- **Problem Solved**: Eliminates configuration drift, unmonitored crashes, and unhandled SIGINT/SIGTERM terminations.

## 🎬 Scenarios (Gherkin)

### Scenario 1: Clean Startup with Valid Configuration
- **Given** the ecosystem configuration file `standalone.yaml` is present
- **When** `{name}` is launched
- **Then** it must connect to required capabilities without panicking
- **And** it must log an initial startup confirmation via universal-logger
- **And** it must register cleanly with the process lifecycle manager

### Scenario 2: Graceful Termination on OS Signal
- **Given** `{name}` is running
- **When** a SIGINT or SIGTERM signal is received
- **Then** the service must execute all registered shutdown hooks
- **And** it must flush active log buffers
- **And** it must exit with status code 0

## 🛠️ Technical Constraints
- **Bootstrap**: MUST initialize via `microservice-toolbox`.
- **Secrets**: MUST decrypt any `ENC(...)` parameters on demand.
"""
    create_file(feat_file, content, dry_run)

    if (brain_dir / "06-Microservices").is_dir():
        svc_doc = brain_dir / "06-Microservices" / f"{name}.md"
        svc_doc_content = f"""---
microservice: {name}
type: specification
status: active
tags:
- '#service/{name}'
- '#type/specification'
- '#state/active'
- '#zone/3-fleet'
---
# 📦 Microservice Specification: {name}

## 🎯 Mission
{desc}

## 🔗 Behavioral Specifications
- [[02-Business-BDD/02-Behavior-Specs/{name}/FEAT-001-Initialization|FEAT-001: Initialization & Lifecycle Management]]
"""
        create_file(svc_doc, svc_doc_content, dry_run)
# -----------------------------------------------------------------------------------------------

def register_sandbox_service(
    brain_dir: pathPath,
    target_dir: pathPath,
    name: str,
    port: int,
    dry_run: bool = False,
    layer: str = "L3"
) -> None:
    """
    When operating inside an isolated sandbox brain or external domain workspace
    (where standalone.yaml is a regular file at brain_dir or brain_dir.parent),
    automatically registers the newly scaffolded microservice capability and repository
    entry in standalone.yaml and 05-Fleet-Operation/00-Repo-Control/{inventory,service-registry}.json.
    """
    brain_standalone = brain_dir / "standalone.yaml"
    workspace_standalone = brain_dir.parent / "standalone.yaml"
    if brain_standalone.is_file() and not brain_standalone.is_symlink():
        standalone_path = brain_standalone
    elif workspace_standalone.is_file() and not workspace_standalone.is_symlink():
        standalone_path = workspace_standalone
    else:
        return
    try:
        raw_yaml = standalone_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return

    cap_name = name.replace("-", "_")
    env_port_key = f"{name.upper().replace('-', '_')}_PORT"

    if dry_run:
        _get_logger().info(f"Scaffolder : [DRY-RUN] Would register capability '{cap_name}' (port {port}) in {standalone_path}")
        return

    if f"    {cap_name}:" not in raw_yaml:
        cap_snippet = (
            f"    {cap_name}:\n"
            f"        ip: ${{HOST_IP:127.0.0.1}}\n"
            f"        port: \"${{{env_port_key}:{port}}}\"\n"
        )
        if "capabilities:\n" in raw_yaml:
            raw_yaml = raw_yaml.replace("capabilities:\n", f"capabilities:\n{cap_snippet}", 1)
        else:
            raw_yaml = raw_yaml.rstrip() + f"\n\ncapabilities:\n{cap_snippet}"
        standalone_path.write_text(raw_yaml, encoding="utf-8")
        _get_logger().info(f"Scaffolder : ✅ Registered capability '{cap_name}' (port {port}) in {standalone_path}")

    repo_ctrl = brain_dir / "05-Fleet-Operation" / "00-Repo-Control"
    inv_file = repo_ctrl / "inventory.json"
    try:
        inv_raw = inv_file.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        _get_logger().info(f"Scaffolder : Sandbox inventory not updated ({exc})")
        inv_raw = ""

    if inv_raw:
        try:
            inv_data = jsonLoads(inv_raw)
            if inv_data.get("isolated_sandbox") or inv_data.get("domain_workspace"):
                repos = inv_data.setdefault("repositories", [])
                if not any(r.get("name") == name for r in repos):
                    try:
                        rel_raw = osPathRelpath(str(target_dir), str(brain_dir))
                        rel_p = rel_raw if rel_raw.startswith("..") else f"./{rel_raw}"
                    except ValueError:
                        rel_p = f"../{name}" if target_dir.parent == brain_dir.parent else f"./06-Microservices/{name}"
                    repos.append({
                        "name": name,
                        "path": rel_p,
                        "remote": f"https://github.com/Bastien-Antigravity/{name}.git",
                        "master_branch": "develop",
                        "layer": layer,
                        "repo_type": f"{layer.lower()}-microservice"
                    })
                    inv_file.write_text(jsonDumps(inv_data, indent=2) + "\n", encoding="utf-8")
        except Exception as e:
            _get_logger().warning(f"Scaffolder : Sandbox inventory update skipped: {e}")

    reg_file = repo_ctrl / "service-registry.json"
    try:
        reg_raw = reg_file.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        _get_logger().info(f"Scaffolder : Sandbox service-registry not updated ({exc})")
        reg_raw = ""

    if reg_raw:
        try:
            reg_data = jsonLoads(reg_raw)
            services = reg_data.setdefault("services", [])
            if not any(s.get("name") == name for s in services):
                services.append({
                    "name": name,
                    "image": f"ghcr.io/bastien-antigravity/{name}",
                    "default_port": port,
                    "protocol": "REST",
                    "layer": layer,
                    "archetype": "Microservice",
                    "classification": f"{layer.lower()}_microservice"
                })
                reg_file.write_text(jsonDumps(reg_data, indent=2) + "\n", encoding="utf-8")
        except Exception as e:
            _get_logger().warning(f"Scaffolder : Sandbox service-registry update skipped: {e}")
