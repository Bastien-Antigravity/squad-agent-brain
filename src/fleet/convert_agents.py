#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Converts the human-readable Role-Prompts from the core-kms-brain into 
compatible Gemini CLI agent definitions in the obsidian-brain vault.

DATA FLOW:
1. Scans core-kms-brain/Role-Prompts for markdown files.
2. Extracts agent names from folder prefixes.
3. Injects mandatory YAML frontmatter and the [SCAN] restoration block.
4. Writes the final agent markdown to obsidian-brain/ :
    gemini      : .agents/skills/ 

KEY PARAMETERS:
- source_dir: Path to the raw role prompts.
- target_dir: Path to the generated Antigravity/Gemini agent definitions.
"""

from argparse import ArgumentParser as argparseArgumentParser
from glob import glob as globGlob
from os import listdir as osListdir, makedirs as osMakedirs, readlink as osReadlink, remove as osRemove, rmdir as osRmdir
from os.path import basename as osPathBasename, dirname as osPathDirname, isdir as osPathIsdir, join as osPathJoin, relpath as osPathRelpath
from pathlib import Path as pathPath
from re import DOTALL as reDotAll, sub as reSub
from typing import List as typeList, Optional as typeOptional, Set as typeSet
import src.bootstrap as bootstrap
from src.lib.orchestration_lib import resolve_vault_and_workspace, get_logger

vault_root, workspace_root = resolve_vault_and_workspace(__file__)

logger = get_logger("ConvertAgents")

# No registry import needed. We output directly to target agent directories.

# -----------------------------------------------------------------------------------------------

def build_skill_markdown(role_name: str, raw_prompt_content: str) -> str:
    """
    Canonical builder for Antigravity IDE SKILL.md files from source Role-Prompts.
    Shared by convert_agents.py and check_coherence.py to guarantee zero template drift.
    """
    clean_body = reSub(r'^---.*?---\s*', '', raw_prompt_content, flags=reDotAll)
    yaml_frontmatter = f"""---
name: {role_name}
description: The {role_name} persona from the Bastien-Antigravity squad.
---
"""
    scan_block = f"""
# 🧭 COMPLEXITY GATE & CANONICAL TOOLBOX CONTRACT (IDE <-> SQUAD LINK)
1. **Complexity Gate (Max 2 Files / Step)**: Before writing code, evaluate whether the request touches >2 files, >2 architectural layers, or multiple languages. If so, decompose it via `TaskDecomposer` (`08-Squad-Agent/src/lib/task_decomposer.py`) into sequential atomic micro-steps.
2. **Canonical `microservice-toolbox` APIs ONLY**:
   - Version: `config.get_version()` / `appConfig.GetVersion()` (never scan directories for `VERSION.txt`).
   - Networking: `config.get_listen_addr(cap)`, `config.get_grpc_listen_addr(cap)`, `config.get_rest_addr(cap)` (never hardcode `127.0.0.1` or ports).
   - Config: Read from `config.get_capability('<service>')` (never chain `os.getenv()` fallbacks in service code; `standalone.yaml` expands `${{VAR:default}}` at boot).
3. **Zero Over-Defensive Bloat (`15-Safe-By-Design-Invariants.md`)**:
   - Never write `hasattr(self.config, ...)` or `isinstance(self.config.data, dict)` on pre-validated `AppConfig`.
   - Never use `asyncio.Lock` without an inner `await`, never wrap Go `atomic.*` in `sync.Mutex`, and never check `os.path.exists()` before `open()` (TOCTOU).
   - Always verify modified files with: `python3 08-Squad-Agent/main.py validate-compliance <path> --strict-imports --strict-lean`.

# 💾 STATE MANAGEMENT RULE (CRITICAL)
Before finishing any major task or concluding a session, you MUST use your available file management tools to append a summary of your actions to the local `AI-Session-State.md` file in the target repository. This acts as our Hard-Stop Context Block to prevent memory loss across sessions.

# 🚨 ATTENTION RESTORATION (SCAN METHOD)
To prevent context degradation, you MUST begin EVERY single response with the following SCAN block:

**[SCAN]** Role: {role_name} | Source: [Source Verification] | State: [Session Progress]
"""
    return yaml_frontmatter + clean_body + "\n" + scan_block

# -----------------------------------------------------------------------------------------------

def _write_compiled_skill(*, target_dir: str, skill_name: str, raw_prompt_content: str, processed_agents: typeSet[str], written_skills: typeList[str]) -> None:
    """Compiles a raw Role-Prompt markdown file and writes <target_dir>/<skill_name>/SKILL.md."""
    if not skill_name or skill_name in processed_agents:
        return
    compiled_skill = build_skill_markdown(skill_name, raw_prompt_content)
    skill_dir = osPathJoin(target_dir, skill_name)
    osMakedirs(skill_dir, exist_ok=True)
    target_file = osPathJoin(skill_dir, "SKILL.md")
    try:
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(compiled_skill)
        logger.info(f"   [Antigravity] Created agent: {skill_name}")
        processed_agents.add(skill_name)
        written_skills.append(skill_name)
    except OSError as e:
        logger.error(f"   ⚠️ Could not write agent {skill_name} to Antigravity: {e}")

# -----------------------------------------------------------------------------------------------

def compile_skills(
    *,
    brain_dir: typeOptional[str] = None,
    merge_core: bool = False,
    out_dir: typeOptional[str] = None,
    skip_workspace_link: bool = False,
) -> typeList[str]:
    """
    Compiles Role-Prompts from a target brain (and optionally central obsidian-brain when
    merge_core=True) into Antigravity SKILL.md directories under out_dir or <brain>/.agents/skills.
    """
    core_vault = pathPath(vault_root).resolve()
    core_workspace = pathPath(workspace_root).resolve()
    target_brain = pathPath(brain_dir).expanduser().resolve() if brain_dir else core_vault
    is_external_brain = target_brain != core_vault

    if out_dir:
        target = str(pathPath(out_dir).expanduser().resolve())
    elif brain_dir:
        target = str(target_brain / ".agents" / "skills")
    else:
        target = osPathJoin(str(core_vault), ".agents", "skills")

    resolved_target = pathPath(target).resolve()
    protected_targets = {
        (core_workspace / ".agents" / "skills").resolve(),
        (core_vault / ".agents" / "skills").resolve(),
    }
    if (out_dir is not None or is_external_brain) and resolved_target in protected_targets:
        raise ValueError(
            f"ConvertAgents : Refusing to overwrite protected core skills directory '{resolved_target}' "
            f"when --out or external --brain is specified."
        )

    source_dirs: typeList[str] = [
        osPathJoin(str(target_brain), "01-Strategic-Nexus", "Role-Prompts"),
        osPathJoin(str(target_brain), "02-Business-BDD", "Role-Prompts"),
        osPathJoin(str(target_brain), "03-Tech-Stack", "Role-Prompts"),
        osPathJoin(str(target_brain), "07-Core-KMS", "Role-Prompts"),
    ]
    if merge_core and is_external_brain:
        source_dirs.extend([
            osPathJoin(str(core_vault), "01-Strategic-Nexus", "Role-Prompts"),
            osPathJoin(str(core_vault), "02-Business-BDD", "Role-Prompts"),
            osPathJoin(str(core_vault), "03-Tech-Stack", "Role-Prompts"),
            osPathJoin(str(core_vault), "07-Core-KMS", "Role-Prompts"),
        ])
    if not brain_dir:
        source_dirs.extend([
            osPathJoin(workspace_root, "core-kms-brain", "Role-Prompts"),
            osPathJoin(workspace_root, "nexus-strategic-brain", "Role-Prompts"),
        ])

    active_source_dirs = [d for d in source_dirs if osPathIsdir(d)]

    try:
        osMakedirs(target, exist_ok=True)
    except OSError as e:
        logger.error(f"   ⚠️ Could not prepare Antigravity agents at {target}: {e}")
        return []

    logger.info(f"🧹 Purging old Antigravity agents in {target}...")
    for f in osListdir(target):
        dir_path = osPathJoin(target, f)
        if osPathIsdir(dir_path):
            skill_md = osPathJoin(dir_path, "SKILL.md")
            try:
                osRemove(skill_md)
                osRmdir(dir_path)
            except FileNotFoundError:
                continue
            except OSError as e:
                logger.error(f"   ⚠️ Could not purge skill {f}: {e}")

    processed_agents: typeSet[str] = set()
    written_skills: typeList[str] = []

    for source_dir in active_source_dirs:
        logger.info(f"📥 Processing roles from: {osPathBasename(osPathDirname(source_dir))}")
        for folder in sorted(osListdir(source_dir)):
            if folder.startswith("."):
                continue
            folder_path = osPathJoin(source_dir, folder)
            if osPathIsdir(folder_path):
                agent_name = folder.split("-", 1)[1].lower() if "-" in folder else folder.lower()
                md_files = sorted(globGlob(osPathJoin(folder_path, "*.md")))
                if md_files:
                    prompt_files = [f for f in md_files if osPathBasename(f).startswith("Prompt-")]
                    md_file = prompt_files[0] if prompt_files else md_files[0]
                    with open(md_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    _write_compiled_skill(
                        target_dir=target,
                        skill_name=agent_name,
                        raw_prompt_content=content,
                        processed_agents=processed_agents,
                        written_skills=written_skills,
                    )
                    for extra_prompt in prompt_files[1:]:
                        extra_stem = osPathBasename(extra_prompt)[len("Prompt-"):-3]
                        extra_name = extra_stem.replace("-", "").replace("_", "").lower()
                        if extra_name and extra_name not in processed_agents:
                            with open(extra_prompt, "r", encoding="utf-8") as f:
                                extra_content = f.read()
                            _write_compiled_skill(
                                target_dir=target,
                                skill_name=extra_name,
                                raw_prompt_content=extra_content,
                                processed_agents=processed_agents,
                                written_skills=written_skills,
                            )

        # Also support arbitrary top-level Prompt-*.md placed directly in Role-Prompts/
        for top_prompt in sorted(globGlob(osPathJoin(source_dir, "Prompt-*.md"))):
            stem = osPathBasename(top_prompt)[len("Prompt-"):-3]
            top_name = stem.replace("-", "").replace("_", "").lower()
            if top_name and top_name not in processed_agents:
                with open(top_prompt, "r", encoding="utf-8") as f:
                    top_content = f.read()
                _write_compiled_skill(
                    target_dir=target,
                    skill_name=top_name,
                    raw_prompt_content=top_content,
                    processed_agents=processed_agents,
                    written_skills=written_skills,
                )

        # Process developer squad language & domain specialists
        squad_path = osPathJoin(source_dir, "03-Developer", "Squad")
        if osPathIsdir(squad_path):
            specialist_map = {
                "pythonspecialist": "Python-Integration-Specialist.md",
                "gospecialist": "Go-Systems-Specialist.md",
                "rustspecialist": "Rust-Safety-Specialist.md",
                "cppspecialist": "CPP-Low-Latency-Specialist.md",
                "webuispecialist": "Web-UI-Specialist.md",
                "timescalespecialist": "Timescale-Data-Specialist.md",
                "vbaspecialist": "Excel-VBA-Specialist.md",
            }
            for spec_name, spec_filename in specialist_map.items():
                if spec_name in processed_agents:
                    continue
                spec_file = osPathJoin(squad_path, spec_filename)
                try:
                    with open(spec_file, "r", encoding="utf-8") as f:
                        content = f.read()
                except FileNotFoundError:
                    continue
                _write_compiled_skill(
                    target_dir=target,
                    skill_name=spec_name,
                    raw_prompt_content=content,
                    processed_agents=processed_agents,
                    written_skills=written_skills,
                )

    # Ensure workspace root .agents/skills symlink points to obsidian-brain/.agents/skills
    # only when compiling for the primary obsidian-brain without custom --out or external --brain.
    if not skip_workspace_link and not out_dir and not is_external_brain and core_vault.name == "obsidian-brain":
        try:
            ws_agents_dir = core_workspace / ".agents"
            ws_skills_link = ws_agents_dir / "skills"
            vault_skills_dir = core_vault / ".agents" / "skills"
            if vault_skills_dir.exists() and core_workspace != core_vault:
                ws_agents_dir.mkdir(parents=True, exist_ok=True)
                rel_target = osPathRelpath(vault_skills_dir, ws_agents_dir)
                if ws_skills_link.is_symlink():
                    if osReadlink(ws_skills_link) != rel_target:
                        ws_skills_link.unlink()
                        ws_skills_link.symlink_to(rel_target)
                elif not ws_skills_link.exists():
                    ws_skills_link.symlink_to(rel_target)
                logger.info(f"🔗 Linked workspace skills: {ws_skills_link} -> {rel_target}")
        except OSError as e:
            logger.warning(f"⚠️ Could not link workspace .agents/skills: {e}")

    return written_skills

# -----------------------------------------------------------------------------------------------

def main() -> None:
    parser = argparseArgumentParser(description="Compile squad role prompts into Antigravity skills.")
    parser.add_argument(
        "--brain",
        type=str,
        default=None,
        help="Target domain brain vault directory whose Role-Prompts should be compiled.",
    )
    parser.add_argument(
        "--merge-core",
        action="store_true",
        help="Merge central obsidian-brain Role-Prompts engineering skills alongside --brain domain personas.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Destination .agents/skills directory (never overwrites Bastien-Antigravity/.agents/skills).",
    )
    parser.add_argument(
        "--skip-workspace-link",
        action="store_true",
        help="Skip updating workspace root .agents/skills symlink (enforced automatically for external brains or --out).",
    )
    args, _ = parser.parse_known_args()

    compile_skills(
        brain_dir=args.brain,
        merge_core=args.merge_core,
        out_dir=args.out,
        skip_workspace_link=args.skip_workspace_link,
    )

# -----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    main()
