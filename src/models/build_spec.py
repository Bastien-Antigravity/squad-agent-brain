#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Defines the canonical cross-brain MicroserviceBuildSpec contract and deterministic
domain port allocator (18100-18999) so external domain brains can hand off structured
feature and architecture specifications to 08-Squad-Agent with zero port collisions
or rule drift.

Failure Policy: Fail-Fast on malformed service slugs, unsupported languages/layers,
or exhausted domain port ranges.

DATA FLOW:
1. Input: Cross-brain task_context / JSON spec + registered workspace standalone.yaml files.
2. Logic: Validates MicroserviceBuildSpec on the cold path and scans reserved fleet/domain ports.
3. Output: Validated MicroserviceBuildSpec with collision-free allocated listen port.

KEY PARAMETERS:
- start_port: Inclusive start of cross-brain dynamic port range (default 18100).
- end_port: Inclusive end of cross-brain dynamic port range (default 18999).
"""

from dataclasses import dataclass as dcDataclass, field as dcField
from json import loads as jsonLoads
from pathlib import Path as pathPath
from re import findall as reFindall, match as reMatch
from typing import Any as typeAny, Dict as typeDict, List as typeList, Optional as typeOptional, Set as typeSet

from src.auditing.validate_compliance import CANONICAL_PORTS

# -----------------------------------------------------------------------------------------------

_VALID_LANGS = frozenset({"go", "python", "rust", "cpp"})
_VALID_LAYERS = frozenset({"L1", "L2", "L3", "L4", "L5"})
_VALID_FLEET_MODES = frozenset({"local", "docker"})
_SLUG_RE = r"^[a-z][a-z0-9-]{1,62}$"

# -----------------------------------------------------------------------------------------------


def collect_reserved_ports(
    *,
    workspace_root: pathPath,
    extra_paths: typeOptional[typeList[pathPath]] = None,
) -> typeSet[int]:
    """Collects all reserved TCP/HTTP/gRPC ports across base fleet and registered domain workspaces."""
    reserved: typeSet[int] = {int(p) for p in CANONICAL_PORTS.keys()}

    scan_files: typeList[pathPath] = []
    native_yaml = workspace_root / "docker-deployment" / "modes" / "local" / "config" / "native.yaml"
    if native_yaml.is_file():
        scan_files.append(native_yaml)

    ws_yaml = workspace_root / "standalone.yaml"
    if ws_yaml.is_file():
        scan_files.append(ws_yaml)

    reg_yaml = workspace_root / "obsidian-brain" / "09-RAG-Engine" / "workspaces.yaml"
    if reg_yaml.is_file():
        reg_text = reg_yaml.read_text(encoding="utf-8")
        for ws_match in reFindall(r"workspace_path\s*:\s*[\"']?([^\r\n\"'#]+)", reg_text):
            ws_cand = pathPath(ws_match.strip())
            try:
                sib_yaml = ws_cand / "standalone.yaml"
                if sib_yaml.is_file() and sib_yaml not in scan_files:
                    scan_files.append(sib_yaml)
                for reg_file in ws_cand.glob("*-brain/05-Fleet-Operation/00-Repo-Control/service-registry.json"):
                    if reg_file.is_file() and reg_file not in scan_files:
                        scan_files.append(reg_file)
            except OSError:
                continue

    if extra_paths:
        for ep in extra_paths:
            if ep.is_file() and ep not in scan_files:
                scan_files.append(ep)
            elif ep.is_dir():
                cand_yaml = ep / "standalone.yaml"
                if cand_yaml.is_file() and cand_yaml not in scan_files:
                    scan_files.append(cand_yaml)
                for reg_file in ep.glob("**/service-registry.json"):
                    if reg_file.is_file() and reg_file not in scan_files:
                        scan_files.append(reg_file)

    for fpath in scan_files:
        raw = fpath.read_text(encoding="utf-8")
        if fpath.name.endswith(".json"):
            parsed = jsonLoads(raw)
            for svc in parsed.get("services", []):
                dp = svc.get("default_port")
                if dp is not None:
                    reserved.add(int(dp))
        else:
            for match in reFindall(r"(?:port|rest_port|grpc_port|http_port)\s*:\s*[\"']?(?:\$\{[A-Z0-9_]+:-?(\d+)\}|(\d+))", raw):
                port_str = match[0] or match[1]
                if port_str:
                    reserved.add(int(port_str))

    return reserved


# -----------------------------------------------------------------------------------------------


def allocate_domain_port(
    *,
    workspace_root: pathPath,
    extra_paths: typeOptional[typeList[pathPath]] = None,
    start_port: int = 18100,
    end_port: int = 18999,
) -> int:
    """Deterministically allocates the lowest unused domain microservice port in [start_port, end_port]."""
    if start_port < 1024 or end_port > 65535 or start_port > end_port:
        raise ValueError(f"Invalid domain port allocation window [{start_port}, {end_port}].")

    reserved = collect_reserved_ports(workspace_root=workspace_root, extra_paths=extra_paths)
    for candidate in range(start_port, end_port + 1):
        if candidate not in reserved:
            return candidate

    raise RuntimeError(f"Exhausted domain port range [{start_port}, {end_port}] — all ports reserved.")


# -----------------------------------------------------------------------------------------------


@dcDataclass
class MicroserviceBuildSpec:
    """Formal cross-brain specification contract for one-shot compliant microservice generation."""

    Name = "MicroserviceBuildSpec"

    service_name: str
    lang: str = "go"
    layer: str = "L3"
    brain_id: str = "obsidian-brain"
    workspace_path: str = ""
    vault_path: str = ""
    port: int = 0
    description: str = "Ecosystem microservice component"
    fleet_mode: str = "local"
    expose_openmfe: bool = True
    expose_grpc: bool = False
    use_nats: bool = False
    use_timescale: bool = False
    bdd_scenarios: typeList[str] = dcField(default_factory=list)

    # -----------------------------------------------------------------------------------------------

    def validate(self) -> None:
        """Fail-fast cold-path validation of cross-brain microservice build parameters."""
        if not reMatch(_SLUG_RE, self.service_name):
            raise ValueError(
                f"Invalid service_name '{self.service_name}': must be kebab-case lowercase (2-63 chars)."
            )
        if self.lang not in _VALID_LANGS:
            raise ValueError(f"Unsupported lang '{self.lang}': expected one of {sorted(_VALID_LANGS)}.")
        if self.layer not in _VALID_LAYERS:
            raise ValueError(f"Unsupported layer '{self.layer}': expected one of {sorted(_VALID_LAYERS)}.")
        if self.fleet_mode not in _VALID_FLEET_MODES:
            raise ValueError(
                f"Unsupported fleet_mode '{self.fleet_mode}': expected one of {sorted(_VALID_FLEET_MODES)}."
            )
        if self.port != 0 and (self.port < 1024 or self.port > 65535):
            raise ValueError(f"Invalid port {self.port}: must be 0 (auto-allocate) or in [1024, 65535].")
        if not self.description.strip():
            raise ValueError("description must be non-empty.")

    # -----------------------------------------------------------------------------------------------

    def resolve_port(self, *, workspace_root: pathPath) -> int:
        """Resolves explicit port (verifying non-collision with base L1/L2 fleet) or auto-allocates."""
        self.validate()
        if self.port > 0:
            if str(self.port) in CANONICAL_PORTS:
                raise ValueError(
                    f"Port {self.port} collides with canonical base port ({CANONICAL_PORTS[str(self.port)]})."
                )
            return self.port

        extra: typeList[pathPath] = []
        if self.workspace_path:
            extra.append(pathPath(self.workspace_path))
        if self.vault_path:
            extra.append(pathPath(self.vault_path))
        self.port = allocate_domain_port(workspace_root=workspace_root, extra_paths=extra)
        return self.port

    # -----------------------------------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: typeDict[str, typeAny]) -> "MicroserviceBuildSpec":
        """Constructs and validates MicroserviceBuildSpec from a JSON/task_context dictionary."""
        spec = cls(
            service_name=str(data.get("service_name") or data.get("name") or "").strip(),
            lang=str(data.get("lang", "go")).strip().lower(),
            layer=str(data.get("layer", "L3")).strip().upper(),
            brain_id=str(data.get("brain_id") or data.get("target_brain_id") or "obsidian-brain").strip(),
            workspace_path=str(data.get("workspace_path") or data.get("target_workspace_path") or "").strip(),
            vault_path=str(data.get("vault_path") or data.get("target_vault_path") or "").strip(),
            port=int(data.get("port", 0)),
            description=str(data.get("description") or data.get("desc") or "Ecosystem microservice component").strip(),
            fleet_mode=str(data.get("fleet_mode", "local")).strip().lower(),
            expose_openmfe=bool(data.get("expose_openmfe", True)),
            expose_grpc=bool(data.get("expose_grpc", False)),
            use_nats=bool(data.get("use_nats", False)),
            use_timescale=bool(data.get("use_timescale", False)),
            bdd_scenarios=list(data.get("bdd_scenarios") or []),
        )
        spec.validate()
        return spec
