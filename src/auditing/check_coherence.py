#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Checks coherence between runtime agent definitions (.agents/skills/) 
and the static source Role-Prompts inside the obsidian-brain submodules.

DATA FLOW:
1. Resolves the vault root dynamically relative to the script path.
2. Iterates over active roles and finds the highest precedence prompt file.
3. Compares the raw contents after stripping frontmatter and sandbox headers.
4. If --fix is set, auto-rebuilds the drifted skill files.
5. Outputs a consistency status report.

KEY PARAMETERS:
- fix: Boolean flag indicating whether to auto-repair drifted agent definitions.
"""

from sys import exit as sysExit, argv as sysArgv
from pathlib import Path
from re import sub as reSub, DOTALL as reDOTALL, IGNORECASE as reIGNORECASE
from argparse import ArgumentParser as argparseArgumentParser
from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths
from lib.orchestration_lib import setup_terminal, resolve_vault_and_workspace, get_logger

# -----------------------------------------------------------------------------------------------

# Setup paths and environment
_self_dir = Path(__file__).resolve().parent
_vault_root = ensure_virtualenv(str(_self_dir))
prepend_venv_bin(_vault_root)
ensure_import_paths(_self_dir, _vault_root)

setup_terminal()
VAULT_ROOT, WORKSPACE_ROOT = resolve_vault_and_workspace(__file__)
skills_dir = VAULT_ROOT / ".agents" / "skills"
logger = get_logger("CheckCoherence")

# Precedence matching mapping
ROLES = {
    "oracle": ("07-Core-KMS/Role-Prompts/00-Oracle", "Prompt-Chronos-Oracle.md"),
    "orchestrator": ("07-Core-KMS/Role-Prompts/01-Orchestrator", "Prompt-Orchestrator.md"),
    "architect": ("07-Core-KMS/Role-Prompts/02-Architect", "Prompt-Architect.md"),
    "developer": ("07-Core-KMS/Role-Prompts/03-Developer", "Prompt-Lead-Developer.md"),
    "qa": ("07-Core-KMS/Role-Prompts/04-QA", "Prompt-QA.md"),
    "fleetarchitect": ("07-Core-KMS/Role-Prompts/05-FleetArchitect", "Prompt-Fleet-Architect.md"),
    "docmaintainer": ("07-Core-KMS/Role-Prompts/06-DocMaintainer", "Prompt-DocMaintainer.md"),
    "fleetcommander": ("07-Core-KMS/Role-Prompts/07-FleetCommander", "Prompt-FleetCommander.md"),
    "purger": ("07-Core-KMS/Role-Prompts/08-Purger", "Mister-Straight-to-Goal.md"),
    "sentinel": ("07-Core-KMS/Role-Prompts/09-Sentinel", "Prompt-Sentinel.md"),
    "docindexer": ("07-Core-KMS/Role-Prompts/10-DocIndexer", "Prompt-DocIndexer.md"),
    "codeindexer": ("07-Core-KMS/Role-Prompts/11-CodeIndexer", "Prompt-CodeIndexer.md"),
    "patternsentinel": ("07-Core-KMS/Role-Prompts/12-PatternSentinel", "Prompt-Pattern-Sentinel.md"),
    "prototyper": ("07-Core-KMS/Role-Prompts/13-Prototyper", "Prompt-Prototyper.md"),
    # Developer Squad Specialists
    "pythonspecialist": ("07-Core-KMS/Role-Prompts/03-Developer/Squad", "Python-Integration-Specialist.md"),
    "gospecialist": ("07-Core-KMS/Role-Prompts/03-Developer/Squad", "Go-Systems-Specialist.md"),
    "rustspecialist": ("07-Core-KMS/Role-Prompts/03-Developer/Squad", "Rust-Safety-Specialist.md"),
    "cppspecialist": ("07-Core-KMS/Role-Prompts/03-Developer/Squad", "CPP-Low-Latency-Specialist.md"),
    "webuispecialist": ("07-Core-KMS/Role-Prompts/03-Developer/Squad", "Web-UI-Specialist.md"),
    "timescalespecialist": ("07-Core-KMS/Role-Prompts/03-Developer/Squad", "Timescale-Data-Specialist.md"),
    "vbaspecialist": ("07-Core-KMS/Role-Prompts/03-Developer/Squad", "Excel-VBA-Specialist.md")
}

# -----------------------------------------------------------------------------------------------

def strip_frontmatter(content: str) -> str:
    """Removes the YAML frontmatter block from markdown content."""
    lines = content.splitlines()
    if not lines:
        return ""
    if lines[0].strip() == "---":
        try:
            closing_idx = lines.index("---", 1)
            return "\n".join(lines[closing_idx+1:]).strip()
        except ValueError:
            return content.strip()
    return content.strip()

# -----------------------------------------------------------------------------------------------

def strip_sandbox_headers(content: str) -> str:
    """Removes attention restoration and state management rules added to skills."""
    content = reSub(r'#\s*🚨\s*ATTENTION\s*RESTORATION.*', '', content, flags=reDOTALL | reIGNORECASE)
    content = reSub(r'#\s*💾\s*STATE\s*MANAGEMENT.*', '', content, flags=reDOTALL | reIGNORECASE)
    return content.strip()

# -----------------------------------------------------------------------------------------------

def fix_mismatch(skill_name: str, prompt_file: Path, skill_file: Path) -> bool:
    """Auto-resolves prompt-skill mismatches by copying/formatting source prompt."""
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Strip existing frontmatter
        content = reSub(r'^---.*?---\s*', '', content, flags=reDOTALL)
        
        yaml_frontmatter = f"""---
name: {skill_name}
description: The {skill_name} persona from the Bastien-Antigravity squad.
---
"""
        scan_block = f"""
# 💾 STATE MANAGEMENT RULE (CRITICAL)
Before finishing any major task or concluding a session, you MUST use your available file management tools to append a summary of your actions to the local `AI-Session-State.md` file in the target repository. This acts as our Hard-Stop Context Block to prevent memory loss across sessions.

# 🚨 ATTENTION RESTORATION (SCAN METHOD)
To prevent context degradation, you MUST begin EVERY single response with the following SCAN block:

**[SCAN]** Role: {skill_name} | Source: [Source Verification] | State: [Session Progress]
"""
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        with open(skill_file, 'w', encoding='utf-8') as f:
            f.write(yaml_frontmatter + content + "\n" + scan_block)
            
        logger.info(f"🔧 AUTO-FIXED: Rebuilt [skills/{skill_name}/SKILL.md] from source.")
        return True
    except Exception as e:
        logger.error(f"❌ Fix Failed: Could not auto-repair skill {skill_name}: {e}")
        return False

# -----------------------------------------------------------------------------------------------

def run_coherence_check(should_fix: bool = False) -> bool:
    logger.info("🔍 RUNTIME AGENT SKILLS VS SOURCE PROMPTS COHERENCE AUDIT")
    
    mismatches = 0
    fixed_count = 0
    
    for skill_name, (rel_dir, filename) in ROLES.items():
        skill_file = skills_dir / skill_name / "SKILL.md"
        prompt_file = VAULT_ROOT / rel_dir / filename
        
        if not skill_file.exists():
            logger.warning(f"❌ Missing Skill: [skills/{skill_name}/SKILL.md]")
            if should_fix:
                if fix_mismatch(skill_name, prompt_file, skill_file):
                    fixed_count += 1
                else:
                    mismatches += 1
            else:
                mismatches += 1
            continue
        if not prompt_file.exists():
            logger.warning(f"❌ Missing Source: [{rel_dir}/{filename}]")
            mismatches += 1
            continue
            
        with open(skill_file, "r", encoding="utf-8") as f:
            skill_raw = f.read()
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt_raw = f.read()
            
        skill_clean = strip_sandbox_headers(strip_frontmatter(skill_raw))
        prompt_clean = strip_sandbox_headers(strip_frontmatter(prompt_raw))
        
        # Normalize line endings
        skill_clean = skill_clean.replace("\r\n", "\n").strip()
        prompt_clean = prompt_clean.replace("\r\n", "\n").strip()
        
        if skill_clean == prompt_clean:
            logger.info(f"✅ COHERENT: {skill_name:<16} <-> {filename}")
        else:
            logger.warning(f"⚠️  MISMATCH: {skill_name:<16} <-> {filename}")
            if should_fix:
                if fix_mismatch(skill_name, prompt_file, skill_file):
                    fixed_count += 1
                else:
                    mismatches += 1
            else:
                mismatches += 1
                
                # Show visual line diff
                s_lines = skill_clean.splitlines()
                p_lines = prompt_clean.splitlines()
                min_len = min(len(s_lines), len(p_lines))
                for idx in range(min_len):
                    if s_lines[idx] != p_lines[idx]:
                        logger.info(f"     └─ First difference at line {idx+1}:")
                        logger.info(f"        Skill:  {repr(s_lines[idx])}")
                        logger.info(f"        Prompt: {repr(p_lines[idx])}")
                        break
                    
    if mismatches == 0:
        if fixed_count > 0:
            logger.info(f"✨ SUCCESS: ALL AGENTS COHERENT (AUTO-REPAIRED {fixed_count} SKILLS)")
        else:
            logger.info("✨ SUCCESS: ALL RUNTIME AGENT SKILLS ARE 100% COHERENT WITH VAULT PROMPTS")
        return True
    else:
        logger.warning(f"⚠️  WARNING: DETECTED {mismatches} DRIFTED OR MISALIGNED AGENTS")
        return False

from src.interfaces import Auditor

class CoherenceAuditor(Auditor):
    """
    Auditor implementation checking coherence between runtime skills and vault prompts.
    """
    def audit(self, should_fix: bool = False, *args, **kwargs) -> bool:
        return run_coherence_check(should_fix=should_fix)

# -----------------------------------------------------------------------------------------------

def main():
    parser = argparseArgumentParser(description="Audit agent prompt coherence")
    parser.add_argument("--fix", action="store_true", help="Auto-resolve prompt-skill mismatches")
    args = parser.parse_args()
    
    auditor = CoherenceAuditor()
    success = auditor.audit(should_fix=args.fix)
    sysExit(0 if success else 1)

if __name__ == "__main__":
    main()
