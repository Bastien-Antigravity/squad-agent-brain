#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
CLI entrypoint and orchestration facade for scaffolding Bastien-Antigravity microservices,
delegating language-specific code generation to modular single-concern generators under
src.lifecycle.scaffolder.

DATA FLOW:
1. Input: CLI arguments (--name, --lang, --port, --layer, --brain, --dest, --fleet-mode).
2. Logic: Resolves target workspace/brain topology, auto-allocates domain port when port=0,
   invokes the selected language generator + common/BDD/registry builders.
3. Output: Production-ready microservice repository and 8-touchpoint registration checklist.

KEY PARAMETERS:
- --name: Kebab-case microservice identifier (e.g., market-observer).
- --lang: Implementation language ('go', 'python', 'rust', 'cpp').
- --port: Primary listen port (or 0 to auto-allocate in 18100-18999).
"""

from argparse import ArgumentParser as argparseArgumentParser
from pathlib import Path as pathPath
from sys import exit as sysExit

from src.lifecycle.scaffolder import (
    _is_external_domain_workspace,
    create_file,
    create_symlink,
    generate_bdd_spec,
    generate_common_files,
    generate_cpp_scaffold,
    generate_go_scaffold,
    generate_openmfe_component_js,
    generate_python_scaffold,
    generate_rust_scaffold,
    register_sandbox_service,
    resolve_workspace_root,
)

# -----------------------------------------------------------------------------------------------

def main() -> None:
    parser = argparseArgumentParser(description="Fabricate a standard Bastien-Antigravity microservice skeleton.")
    parser.add_argument("--name", "-n", help="Microservice name (e.g. market-observer)")
    parser.add_argument("--lang", "-l", choices=["go", "python", "rust", "cpp"], default="go", help="Language (go, python, rust, cpp)")
    parser.add_argument("--port", "-p", type=int, default=8190, help="Default capability listen port")
    parser.add_argument("--layer", choices=["L1", "L2", "L3", "L4", "L5"], default="L3", help="Architecture layer (L1..L5, defaults to L3)")
    parser.add_argument("--desc", "-d", default="Ecosystem microservice component", help="Short mission description")
    parser.add_argument("--dest", help="Destination path (defaults to ../<name> or <brain>/06-Microservices/<name> in sandbox mode)")
    parser.add_argument("--brain", help="Target knowledge brain directory (defaults to domain brain or obsidian-brain)")
    parser.add_argument("--fleet-mode", choices=["local", "docker"], default="local", help="Base fleet config target for standalone.yaml ('local' -> native.yaml on 127.0.0.1, 'docker' -> host-bridge.yaml on 127.0.0.2)")
    parser.add_argument("--sandbox", "--isolated", dest="sandbox", action="store_true", help="Scaffold inside the target satellite brain's 06-Microservices/<name> folder and register in sandbox standalone.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Preview file fabrication without writing to disk")

    args = parser.parse_args()

    name = args.name
    if not name:
        name = input("Enter new microservice name (e.g. market-observer): ").strip()
        if not name:
            print("❌ Error: Service name is required.")
            sysExit(1)

    lang = args.lang
    port = args.port
    layer = args.layer
    desc = args.desc
    dry_run = args.dry_run

    workspace_root = resolve_workspace_root()
    if args.brain:
        brain_dir = pathPath(args.brain).expanduser().resolve()
    elif (pathPath.cwd() / "02-Business-BDD").exists() and (pathPath.cwd() / "06-Microservices").exists():
        brain_dir = pathPath.cwd().resolve()
    elif (pathPath.cwd() / "standalone.yaml").is_file() and not (pathPath.cwd() / "standalone.yaml").is_symlink():
        child_brains = [
            d for d in pathPath.cwd().iterdir()
            if d.is_dir() and (d / "02-Business-BDD").is_dir() and (d / "06-Microservices").is_dir()
        ]
        brain_dir = child_brains[0].resolve() if len(child_brains) == 1 else (workspace_root / "obsidian-brain")
    else:
        brain_dir = workspace_root / "obsidian-brain"

    is_external_workspace = _is_external_domain_workspace(brain_dir, workspace_root)
    is_satellite_sandbox = (
        not is_external_workspace
        and (
            args.sandbox
            or brain_dir.name != "obsidian-brain"
            or (
                (brain_dir / "standalone.yaml").is_file()
                and not (brain_dir / "standalone.yaml").is_symlink()
            )
        )
    )

    if args.dest:
        target_dir = pathPath(args.dest).expanduser().resolve()
    elif is_external_workspace:
        target_dir = (brain_dir.parent / name).resolve()
    elif is_satellite_sandbox:
        target_dir = (brain_dir / "06-Microservices" / name).resolve()
    else:
        target_dir = workspace_root / name
        if not args.brain and (target_dir.parent / "obsidian-brain").exists():
            brain_dir = target_dir.parent / "obsidian-brain"

    if port == 0:
        from src.models.build_spec import allocate_domain_port
        port = allocate_domain_port(
            workspace_root=workspace_root,
            extra_paths=[brain_dir.parent, brain_dir],
        )
        print(f"🔌 Auto-allocated collision-free domain port: {port}")

    print(f"\n🚀 Fabricating microservice '{name}' ({lang}, {layer}) at {target_dir}...")

    if target_dir.exists() and not dry_run:
        print(f"⚠️ Warning: Target directory {target_dir} already exists. Proceeding with caution.")

    # 1. Generate language specific scaffold
    if lang == "go":
        generate_go_scaffold(target_dir, name, port, desc, dry_run, layer=layer, brain_name=brain_dir.name)
    elif lang == "python":
        generate_python_scaffold(target_dir, name, port, desc, dry_run, layer=layer, brain_name=brain_dir.name)
    elif lang == "rust":
        generate_rust_scaffold(target_dir, name, port, desc, dry_run, layer=layer, brain_name=brain_dir.name)
    elif lang == "cpp":
        generate_cpp_scaffold(target_dir, name, port, desc, dry_run, layer=layer, brain_name=brain_dir.name)

    # 2. Generate common ecosystem files
    generate_common_files(target_dir, name, lang, port, desc, dry_run, layer=layer, fleet_mode=args.fleet_mode)

    # 3. Generate BDD specification stub & 06-Microservices/<name>.md
    generate_bdd_spec(brain_dir, name, desc, dry_run)

    # 4. Auto-register in domain/sandbox standalone.yaml and inventory
    if is_external_workspace or is_satellite_sandbox:
        register_sandbox_service(brain_dir, target_dir, name, port, dry_run, layer=layer)

    cap_name = name.replace("-", "_")

    print("\n" + "=" * 80)
    print(f"🎉 Microservice '{name}' successfully scaffolded!")
    print("=" * 80)
    print("\n📋 REQUIRED FLEET REGISTRATION CHECKLIST (THE 8 TOUCHPOINTS):")
    print("1. [docker-deployment/modes/local/config/native.yaml] Add capability:")
    print(f"""       {cap_name}:
           ip: ${{HOST_IP:-127.0.0.1}}
           port: "${{{name.upper().replace('-', '_')}_PORT:-{port}}}"
""")
    print(f"2. [docker-deployment/modes/docker/config/services/{name}.yaml] Create container config slice:")
    print(f"""       capabilities:
         {cap_name}:
           ip: 0.0.0.0
           port: "{port}"
         nats_server:
           ip: nats-server
           port: 4222
         log_server:
           ip: log-server
           port: 9020
         config_server:
           ip: config-server
           port: 3306
         timescale_db:
           ip: timescale-db
           port: 5432
""")
    print("3. [docker-deployment/docker-compose.yaml] Add service container:")
    print(f"""     {name}:
       image: ghcr.io/bastien-antigravity/{name}:${{TAG:-develop}}
       build:
         context: ../{name}
         dockerfile: Dockerfile
       container_name: {name}
       restart: unless-stopped
       volumes:
         - ./modes/docker/config/services/{name}.yaml:/{name}/standalone.yaml:ro
       networks:
         teleremote-network:
           aliases:
             - {name}
""")
    print("4. [watchdog-agent/src/config/heal.go] Add symlink target:")
    print(f'       filepath.Join(rootDir, "{name}", "standalone.yaml"),\n')
    print("5. [docker-deployment/scripts/common.py] Add to SERVICES_SPEC (for fleet.sh compile/status):")
    if lang == "go":
        bin_rel = f"{name}/bin/{name}"
        build_c = f'["go", "build", "-o", "bin/{name}" + EXE_EXT, "./cmd/{name}"]'
    elif lang == "rust":
        bin_rel = f"{name}/target/debug/{name}"
        build_c = '["cargo", "build"]'
    elif lang == "cpp":
        bin_rel = f"{name}/bin/{name}"
        build_c = '["make", "build"]'
    else:
        bin_rel = ""
        build_c = "None"
    print(f"""       {{
         "name": "{name}",
         "proc_pattern": "{name}",
         "win_exe": "{name}.exe",
         "rel_dir": "{name}",
         "build_cmd": {build_c},
         "bin_path": "{bin_rel}" + EXE_EXT,
         "port": {port},
         "protocol": "REST",
       }}
""")
    print("6. [obsidian-brain/05-Fleet-Operation/00-Repo-Control/service-registry.json] Register service:")
    print(f"""       {{
         "name": "{name}",
         "image": "ghcr.io/bastien-antigravity/{name}",
         "default_port": {port},
         "protocol": "REST",
         "archetype": "Microservice",
         "classification": "level1_microservice"
       }}
""")
    print("7. [obsidian-brain/05-Fleet-Operation/00-Repo-Control/inventory.json] Register repository:")
    print(f"""       {{
         "name": "{name}",
         "path": "./{name}",
         "remote": "https://github.com/Bastien-Antigravity/{name}.git",
         "master_branch": "develop",
         "repo_type": "level1-microservice"
       }}
       (Or run: python3 obsidian-brain/08-Squad-Agent/main.py build-inventory)
""")
    print("8. [UI & Remote Integration] (Optional / If Interactive):")
    print("   - OpenMFE & Service Spec: Auto-registers with web-interface via spec.PublishWithLifecycle (Go) / spec.publish_with_lifecycle (Python) / spec::publish_with_lifecycle (Rust) / SpecPublisher::PublishWithLifecycle (C++)")
    print("   - Exchange Contracts: Expose GET /api/v1/contracts & populate ServiceSpec.Contracts (Go/Python/Rust/C++) -> rendered via BastienMFEContracts in .openmfe-tabs-bar")
    print("   - Tele-Remote: Push dynamic UI menu over gRPC (Port 1863)")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
