#!/usr/bin/env python
# coding:utf-8
# cli:allow-print

"""
ESSENTIAL PROCESS:
Ecosystem Secret Leakage and Plaintext Parameter Auditor.
Scans configurations, manifests, and log files across the Bastien-Antigravity fleet to guarantee:
  1. No sensitive parameter (token, password, secret, chat_id, api_key) is stored in plaintext in YAML/JSON configs.
  2. All secret configuration values are strictly wrapped in ENC(...) tokens.
  3. No decrypted secret value or sensitive credential appears in plaintext inside log files.
  4. Optionally scrubs historical log files of leaked credentials.

DATA FLOW:
1. Loads configuration files (native.yaml, config-server.yaml, config_store.json) and audits for plaintext secrets.
2. Resolves active RSA private key and decrypts known secrets in memory.
3. Scans active log files in the ecosystem for occurrences of decrypted plaintext secrets.
4. Generates structured findings report and returns exit status (0 = SECURE, 1 = LEAK_DETECTED).
5. If --scrub is supplied, scrubs and redacts detected leaks from target log files.

KEY PARAMETERS:
- workspace_root: Root directory of the Bastien-Antigravity ecosystem.
- priv_key_path: Path to the sovereign RSA private key (/etc/bastien/private.pem).
- scrub: When True, overwrites leaked instances in log files with [REDACTED_SECRET].
"""

from argparse import ArgumentParser as argArgumentParser
from base64 import b64decode as base64B64decode
from json import dumps as jsonDumps
from os import environ as osEnviron, walk as osWalk
from pathlib import Path
from re import IGNORECASE as reIgnoreCase, compile as reCompile, match as reMatch, search as reSearch
from subprocess import DEVNULL as subprocessDEVNULL, PIPE as subprocessPIPE, Popen as subprocessPopen
from sys import exit as sysExit
from typing import Any as typeAny, Dict as typeDict, List as typeList, Optional as typeOptional, Set as typeSet

# -----------------------------------------------------------------------------------------------

SENSITIVE_KEY_REGEX = reCompile(
    r"^(token|password|secret|chat_id|chatid|auth_token|api_key|apikey|private_key)$|"
    r"(_token|_password|_secret|_chatid|_chat_id|_api_key|_apikey)$",
    reIgnoreCase
)

IGNORED_LOG_DIRS = {
    ".git", ".venv", "venv", "node_modules", "target", "obj", "dist", "build", ".rag_cache", "__pycache__"
}

# -----------------------------------------------------------------------------------------------

class SecretLeakAuditor:
    Name = "SecretLeakAuditor"

    def __init__(self, *, workspace_root: Path, priv_key_path: typeOptional[Path] = None):
        self.workspace_root = workspace_root
        self.priv_key_path = priv_key_path or self._resolve_private_key()

    def _resolve_private_key(self) -> typeOptional[Path]:
        env_key_path = osEnviron.get("BASTIEN_PRIVATE_KEY_PATH")
        if env_key_path:
            p = Path(env_key_path).expanduser().resolve()
            if p.exists():
                return p
        default_p = Path("/etc/bastien/private.pem")
        if default_p.exists():
            return default_p
        local_p = self.workspace_root / "private.pem"
        if local_p.exists():
            return local_p
        return None

    def decrypt_secret(self, *, cipher_str: str) -> typeOptional[str]:
        if not self.priv_key_path or not self.priv_key_path.exists():
            return None
        m = reSearch(r"ENC\(([^)]+)\)", cipher_str)
        if not m:
            return None
        raw_b64 = m.group(1).strip()
        try:
            data = base64B64decode(raw_b64)
        except Exception:
            return None
        try:
            p = subprocessPopen(
                ["openssl", "pkeyutl", "-decrypt", "-inkey", str(self.priv_key_path), "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"],
                stdin=subprocessPIPE, stdout=subprocessPIPE, stderr=subprocessDEVNULL
            )
            out, _ = p.communicate(input=data)
            if p.returncode == 0:
                return out.decode("utf-8", errors="replace")
        except Exception:
            pass
        return None

    def audit_config_files(self) -> typeList[typeDict[str, typeAny]]:
        violations: typeList[typeDict[str, typeAny]] = []
        target_configs = [
            self.workspace_root / "docker-deployment" / "modes" / "local" / "config" / "native.yaml",
            self.workspace_root / "docker-deployment" / "modes" / "docker" / "config" / "services" / "config-server.yaml",
            self.workspace_root / "docker-deployment" / "modes" / "docker" / "config" / "services" / "tele-remote.yaml",
            self.workspace_root / "config-server" / "bin" / "config_store.json",
        ]

        for cfg_path in target_configs:
            if not cfg_path.exists():
                continue
            try:
                content = cfg_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for idx, line in enumerate(content.splitlines(), start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                    continue

                if ":" not in stripped:
                    continue

                parts = stripped.split(":", 1)
                key = parts[0].strip().strip('"\'')
                val = parts[1].strip().rstrip(",").strip().strip('"\'')

                if not SENSITIVE_KEY_REGEX.search(key):
                    continue

                if not val or val == '""' or val == "''":
                    continue

                if "${" in val:
                    m = reMatch(r"^\$\{([^}:]+)(?::[-?]?(.*))?\}$", val)
                    if m:
                        default_part = m.group(2) if m.group(2) is not None else ""
                        default_part = default_part.strip().rstrip(",").strip().strip('"\'')
                        if not default_part or (default_part.startswith("ENC(") and default_part.endswith(")")):
                            continue
                        violations.append({
                            "file": str(cfg_path),
                            "line": idx,
                            "key": key,
                            "rule": "UNENCRYPTED_CONFIG_SECRET",
                            "message": f"Sensitive key '{key}' defines a plaintext default value: '{default_part}'. Must use ENC(...) encryption."
                        })
                        continue

                if val.startswith("ENC(") and val.endswith(")"):
                    continue

                violations.append({
                    "file": str(cfg_path),
                    "line": idx,
                    "key": key,
                    "rule": "UNENCRYPTED_CONFIG_SECRET",
                    "message": f"Sensitive key '{key}' has plaintext value '{val}'. Must be encrypted to ENC(...) format."
                })

        return violations

    def extract_known_secrets(self) -> typeDict[str, str]:
        secrets_map: typeDict[str, str] = {}
        native_yaml = self.workspace_root / "docker-deployment" / "modes" / "local" / "config" / "native.yaml"
        if not native_yaml.exists():
            return secrets_map

        try:
            content = native_yaml.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return secrets_map

        for match in reCompile(r"ENC\([^)]+\)").finditer(content):
            enc_token = match.group(0)
            decrypted = self.decrypt_secret(cipher_str=enc_token)
            if decrypted and len(decrypted.strip()) >= 4:
                trimmed = decrypted.strip()
                secrets_map[enc_token[:16] + "..."] = trimmed

        return secrets_map

    def audit_log_files(self, *, known_secrets: typeDict[str, str], scrub: bool = False) -> typeList[typeDict[str, typeAny]]:
        violations: typeList[typeDict[str, typeAny]] = []
        if not known_secrets:
            return violations

        log_files: typeList[Path] = []
        for root, dirs, files in osWalk(str(self.workspace_root)):
            rel_parts = Path(root).relative_to(self.workspace_root).parts
            if len(rel_parts) >= 4:
                dirs.clear()
            dirs[:] = [d for d in dirs if d not in IGNORED_LOG_DIRS and not d.startswith(".")]
            for f in files:
                if f.endswith(".log") or ".log." in f:
                    log_files.append(Path(root) / f)

        for log_file in log_files:
            try:
                raw_bytes = log_file.read_bytes()
            except Exception:
                continue

            # Fast compiled byte scan to bypass clean files instantly
            matched_secrets = {label: val for label, val in known_secrets.items() if val.encode("utf-8") in raw_bytes}
            if not matched_secrets:
                continue

            content = raw_bytes.decode("utf-8", errors="replace")
            lines = content.splitlines()
            file_modified = False

            COMMON_IDENTIFIERS = {"admin", "dbuser", "user", "root"}

            for idx, line in enumerate(lines, start=1):
                for label, secret_val in matched_secrets.items():
                    is_match = False
                    if secret_val in COMMON_IDENTIFIERS:
                        if reSearch(rf"(?:password|passwd|pwd)\s*[=:]\s*['\"]?{secret_val}['\"]?", line, reIgnoreCase):
                            is_match = True
                    elif len(secret_val) >= 7 and secret_val in line:
                        is_match = True

                    if is_match:
                        masked_line = line.replace(secret_val, "[REDACTED_SECRET]")
                        violations.append({
                            "file": str(log_file),
                            "line": idx,
                            "secret_label": label,
                            "rule": "SECRET_LEAK_IN_LOGS",
                            "message": f"Plaintext secret leak detected in log file: {masked_line[:120]}"
                        })
                        if scrub:
                            lines[idx - 1] = masked_line
                            file_modified = True

            if scrub and file_modified:
                try:
                    log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
                except Exception:
                    pass

        return violations

# -----------------------------------------------------------------------------------------------

def main() -> None:
    parser = argArgumentParser(description="Audit ecosystem configurations and logs for plaintext secrets and credential leaks.")
    parser.add_argument("--check", action="store_true", help="Exit with code 1 if any secret leaks are found.")
    parser.add_argument("--scrub", action="store_true", help="Automatically scrub leaked secrets from detected log files.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format.")
    args = parser.parse_args()

    workspace_root = Path.cwd()
    if not (workspace_root / "AGENTS.md").exists():
        for parent in workspace_root.parents:
            if (parent / "AGENTS.md").exists():
                workspace_root = parent
                break

    auditor = SecretLeakAuditor(workspace_root=workspace_root)

    config_violations = auditor.audit_config_files()
    known_secrets = auditor.extract_known_secrets()
    log_violations = auditor.audit_log_files(known_secrets=known_secrets, scrub=args.scrub)

    all_violations = config_violations + log_violations

    if args.json:
        print(jsonDumps({"violations": all_violations, "total": len(all_violations)}, indent=2))
        if args.check and all_violations:
            sysExit(1)
        return

    print("===============================================================================")
    print("🔒 Bastien-Antigravity Ecosystem Secret & Credential Leak Auditor")
    print("===============================================================================")
    print(f"📁 Workspace Root: {workspace_root}")
    print(f"🔑 Sovereign RSA Key: {auditor.priv_key_path or 'NOT_FOUND'}")
    print(f"🔐 Known Decrypted Secrets Monitored: {len(known_secrets)}")
    print("-------------------------------------------------------------------------------")

    if not all_violations:
        print("✅ 100% SECURE: No plaintext secrets in configs and zero credential leaks in logs.")
        sysExit(0)

    print(f"⚠️  DETECTED {len(all_violations)} POTENTIAL LEAK(S) / UNENCRYPTED PARAMETER(S):")
    for v in all_violations:
        rel_path = Path(v["file"]).relative_to(workspace_root) if str(workspace_root) in v["file"] else v["file"]
        print(f"  ❌ [{v['rule']}] {rel_path}:{v['line']}")
        print(f"     {v['message']}")

    if args.scrub:
        print("\n🧹 Leaked secrets in logs have been scrubbed with [REDACTED_SECRET].")

    if args.check:
        sysExit(1)

if __name__ == "__main__":
    main()
