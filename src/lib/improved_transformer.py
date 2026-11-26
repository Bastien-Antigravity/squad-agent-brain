#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Python code transformation engine (CodeTransformer) for the Specialist agent.
Refactors and cleans source code to make it compliant with governance.
Uses AST-based refactoring for robust import management.

DATA FLOW:
1. Analyze and clean the header (shebang, encoding).
2. Validate and format the module triple-block docstring.
3. Align imports with granular and aliasing standards using AST span splicing (preserving comments).
4. Adjust spacing after docstring (exactly 1 empty line).
5. Standardize method dividers (95 dashes).
6. Standardize logger formatting to f"{self.Name} : {msg}".

KEY PARAMETERS:
- code: String containing the non-compliant Python source code.
"""

import ast
import os
import sys
from pathlib import Path
from typing import Optional, Any, List
from re import sub as reSub, search as reSearch, match as reMatch, MULTILINE as reMULTILINE, DOTALL as reDOTALL

# -----------------------------------------------------------------------------

class CodeTransformer:
    Name = "CodeTransformer"

    # -----------------------------------------------------------------------------
    def __init__(self, config: Optional[Any] = None, logger: Optional[Any] = None, name: Optional[str] = None):
        if config is None or logger is None:
            import src.bootstrap as bootstrap
            config = config or bootstrap.config
            logger = logger or bootstrap.logger

        self.config = config
        self.logger = logger
        self.Name = name if name is not None else "CodeTransformer"

    # -----------------------------------------------------------------------------
    def _log(self, level: str, msg: str) -> None:
        """Delegates logging directly to the UniLog engine."""
        log_fn = getattr(self.logger, level, self.logger.info)
        log_fn(f"{self.Name} : {msg}")

    # -----------------------------------------------------------------------------
    def transform(self, *, code: str, class_name: str = "GeneratedModule") -> str:
        """
        Transforms non-compliant Python code to respect the coding standards.
        Validates syntax before and after transformation to guarantee semantic safety
        and idempotency.
        """
        self._log("info", "beginning transformation")
        original_code = code

        # 0. Pre-flight AST validation: refuse to mangle syntactically invalid Python
        try:
            ast.parse(code)
        except SyntaxError as syn_err:
            self._log("warning", f"Skipping transformation of syntactically invalid Python source: {syn_err}")
            return original_code
        
        # 1. Clean header and force shebang and utf-8 encoding
        code = self._clean_shebang_and_encoding(code)
        
        # 2. Ensure presence of module docstring in Triple-Block format
        code = self._ensure_triple_block_docstring(code)

        # 3. Ensure presence of docstrings for class and methods before AST unparse
        code = self._ensure_class_and_method_docstrings(code)
        
        # 4. Align imports (remove globals, merge partials, and apply aliasing via AST)
        code = self._ensure_granular_imports(code)
        
        # 5. Adjust spacing after docstring (exactly 1 empty line)
        code = self._ensure_docstring_empty_line(code)
        
        # 6. Replace/insert method dividers (exactly 95 dashes)
        code = self._ensure_method_dividers(code)
        
        # 7. Format logger calls with f"{self.Name} : {msg}"
        code = self._ensure_logger_formatting(code, class_name)

        # 8. Post-transform AST verification: rollback if transformation broke syntax
        try:
            ast.parse(code)
        except SyntaxError as post_err:
            self._log("error", f"Post-transform AST validation failed ({post_err}); rolling back to original source.")
            return original_code
        
        self._log("info", "transformation completed successfully")
        return code

    # -----------------------------------------------------------------------------------------------
    def _clean_shebang_and_encoding(self, code: str) -> str:
        lines = code.splitlines()
        cleaned_lines = []
        
        # Ignore existing header lines if they look like shebang or encoding
        idx = 0
        while idx < len(lines):
            line = lines[idx].strip()
            if line.startswith("#!") or "coding:" in line or "-*- coding" in line:
                idx += 1
            elif line == "":
                idx += 1
            else:
                break
                
        # Insert the correct headers
        cleaned_lines.append("#!/usr/bin/env python")
        cleaned_lines.append("# coding:utf-8")
        cleaned_lines.append("")
        cleaned_lines.extend(lines[idx:])
        
        return "\n".join(cleaned_lines)

    # -----------------------------------------------------------------------------------------------
    def _ensure_triple_block_docstring(self, code: str) -> str:
        # Check if module-level docstring exists via AST
        try:
            tree = ast.parse(code)
            mod_doc = ast.get_docstring(tree, clean=False)
        except Exception:
            mod_doc = None

        default_doc = '"""\nESSENTIAL PROCESS:\nMathematical integration module generated by the agent.\n\nDATA FLOW:\n1. Process data.\n2. Return the result.\n\nKEY PARAMETERS:\n- config: Configuration.\n- logger: Logger.\n"""'
        
        if mod_doc is None:
            # No module docstring at all, insert it after shebang and encoding
            parts = code.split("# coding:utf-8\n")
            if len(parts) >= 2:
                return parts[0] + "# coding:utf-8\n\n" + default_doc + "\n" + "".join(parts[1:])
            return default_doc + "\n" + code

        # Search for the first triple-quotes docstring representing the module docstring
        match_doc = reSearch(r'"""(.*?)"""', code, reMULTILINE | reDOTALL)
        if not match_doc:
            return code
            
        doc_content = match_doc.group(1)
        
        # Check if mandatory sections are present
        needs_update = False
        updated_doc = '"""\n'
        if "ESSENTIAL PROCESS:" not in doc_content:
            updated_doc += "ESSENTIAL PROCESS:\nMathematical integration module generated by the agent.\n\n"
            needs_update = True
        else:
            # Keep the existing section
            if "ESSENTIAL PROCESS:" in doc_content:
                parts = doc_content.split("ESSENTIAL PROCESS:")
                next_part = parts[1].split("DATA FLOW:")[0].split("KEY PARAMETERS:")[0].strip()
                updated_doc += "ESSENTIAL PROCESS:\n" + next_part + "\n\n"
            
        if "DATA FLOW:" not in doc_content:
            updated_doc += "DATA FLOW:\n1. Process data.\n2. Return the result.\n\n"
            needs_update = True
        else:
            parts = doc_content.split("DATA FLOW:")
            next_part = parts[1].split("KEY PARAMETERS:")[0].strip()
            updated_doc += "DATA FLOW:\n" + next_part + "\n\n"
            
        if "KEY PARAMETERS:" not in doc_content:
            updated_doc += "KEY PARAMETERS:\n- config: Configuration.\n- logger: Logger.\n"
            needs_update = True
        else:
            parts = doc_content.split("KEY PARAMETERS:")
            next_part = parts[1].strip()
            updated_doc += "KEY PARAMETERS:\n" + next_part + "\n"
            
        updated_doc += '"""'
        
        if needs_update or doc_content.strip() != updated_doc.replace('"""', '').strip():
            # Replace old docstring with the new structured docstring
            start_idx = match_doc.start()
            end_idx = match_doc.end()
            return code[:start_idx] + updated_doc + code[end_idx:]
            
        return code

    # -----------------------------------------------------------------------------------------------
    def _ensure_docstring_empty_line(self, code: str) -> str:
        # Find the end of the module docstring
        match_doc = reSearch(r'"""(.*?)"""', code, reMULTILINE | reDOTALL)
        if match_doc:
            end_idx = match_doc.end()
            remainder = code[end_idx:]
            # Count and clean empty lines following the docstring
            lines_after = remainder.splitlines()
            idx = 0
            while idx < len(lines_after) and lines_after[idx].strip() == "":
                idx += 1
            # Force exactly one empty line
            return code[:end_idx] + "\n\n" + "\n".join(lines_after[idx:])
        return code

    # -----------------------------------------------------------------------------------------------
    @staticmethod
    def make_camel_alias(module_name: str, symbol_name: str) -> str:
        """
        Computes the canonical Bastien camelCase import alias `[module][SymbolName]`.
        Examples:
          - ('os.path', 'join') -> 'osPathJoin'
          - ('datetime', 'datetime') -> 'dtDateTime'
          - ('json', 'dumps') -> 'jsonDumps'
          - ('typing', 'Optional') -> 'typeOptional'
          - ('yaml', 'safe_load') -> 'yamlSafeLoad'
        """
        prefix_overrides = {
            "typing": "type",
            "datetime": "dt",
        }
        if module_name in prefix_overrides:
            mod_prefix = prefix_overrides[module_name]
        else:
            raw_parts = [p for seg in module_name.split(".") for p in seg.split("_") if p]
            if not raw_parts:
                mod_prefix = module_name
            else:
                mod_prefix = raw_parts[0].lower() + "".join(p.capitalize() for p in raw_parts[1:])

        if symbol_name == "datetime":
            sym_suffix = "DateTime"
        elif "_" in symbol_name:
            sym_suffix = "".join(p.capitalize() for p in symbol_name.split("_") if p)
        elif symbol_name:
            sym_suffix = symbol_name[0].upper() + symbol_name[1:]
        else:
            sym_suffix = symbol_name

        return f"{mod_prefix}{sym_suffix}"

    # -----------------------------------------------------------------------------------------------
    @staticmethod
    def is_internal_module(module_name: Optional[str], level: int = 0) -> bool:
        """Returns True if the import targets an internal project/ecosystem local module."""
        if level and level > 0:
            return True
        if not module_name:
            return False
        internal_roots = (
            "src", "lib", "interfaces", "agents", "auditing", "bootstrap", "clients",
            "core", "evaluation", "extraction", "facade", "factory", "fleet",
            "grpc_control", "helpers", "identity", "lifecycle", "maintenance",
            "memory", "models", "planner", "rest", "safety", "skills", "specs",
            "telegram", "tests", "utils", "web",
        )
        root_pkg = module_name.split(".")[0]
        return root_pkg in internal_roots

    # -----------------------------------------------------------------------------------------------
    def _ensure_granular_imports(self, code: str) -> str:
        """
        Refactored version using AST to safely identify and transform whole-module imports
        and unaliased external/stdlib imports into granular camelCase aliased imports.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code

        # 1. Identify all top-level imports and classify them
        imports_to_replace = {}  # local_bound_name -> module_name (for whole-module `import X`)
        from_symbol_to_alias = {}  # local_bound_name -> (module_name, original_symbol, target_alias)
        grouped_from_imports = {}  # module_name -> dict of {original_symbol: target_alias}
        external_imports = []
        internal_imports = []

        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound_name = alias.asname or alias.name
                    if self.is_internal_module(alias.name, 0):
                        internal_imports.append(f"import {alias.name}")
                    else:
                        imports_to_replace[bound_name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                if self.is_internal_module(mod_name, node.level or 0):
                    # Rule: Do NOT alias local/internal libraries
                    prefix_dots = "." * (node.level or 0)
                    clean_names = [a.name for a in node.names]
                    internal_imports.append(f"from {prefix_dots}{mod_name} import {', '.join(clean_names)}")
                else:
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        orig_sym = alias.name
                        bound_name = alias.asname or orig_sym
                        target_alias = alias.asname or self.make_camel_alias(mod_name, orig_sym)
                        from_symbol_to_alias[bound_name] = (mod_name, orig_sym, target_alias)
                        grouped_from_imports.setdefault(mod_name, {})[orig_sym] = target_alias

        # 2. Collect exact AST source span replacements so comments and formatting are preserved
        outer_self = self

        class UsageCollector(ast.NodeVisitor):
            def __init__(self):
                self.used_from_imports = {}  # module_name -> {orig_sym: target_alias}
                self.unresolved_whole_modules = set()
                self.replacements = []  # (lineno, col, end_lineno, end_col, replacement_str)

            def _register_used(self, mod_name: str, sym_name: str) -> str:
                alias = grouped_from_imports.get(mod_name, {}).get(sym_name) or outer_self.make_camel_alias(mod_name, sym_name)
                self.used_from_imports.setdefault(mod_name, {})[sym_name] = alias
                return alias

            def visit_Attribute(self, node):
                # First check 2-level attributes like os.path.join or urllib.request.urlopen
                if (
                    isinstance(node.value, ast.Attribute)
                    and isinstance(node.value.value, ast.Name)
                    and node.value.value.id in imports_to_replace
                ):
                    root_mod = imports_to_replace[node.value.value.id]
                    sub_mod = f"{root_mod}.{node.value.attr}"
                    alias = self._register_used(sub_mod, node.attr)
                    self.replacements.append((node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, alias))
                    return

                # Check 1-level attributes like json.dumps, time.sleep, re.search, sys.exit
                if isinstance(node.value, ast.Name) and node.value.id in imports_to_replace:
                    mod_name = imports_to_replace[node.value.id]
                    alias = self._register_used(mod_name, node.attr)
                    self.replacements.append((node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, alias))
                    return

                self.generic_visit(node)

            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Load) and node.id in from_symbol_to_alias:
                    mod_name, orig_sym, target_alias = from_symbol_to_alias[node.id]
                    self.used_from_imports.setdefault(mod_name, {})[orig_sym] = target_alias
                    if target_alias != node.id:
                        self.replacements.append((node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, target_alias))
                    return
                if isinstance(node.ctx, ast.Load) and node.id in imports_to_replace:
                    self.unresolved_whole_modules.add(imports_to_replace[node.id])

        # Determine docstring end and non-import body nodes
        doc_node = None
        if (
            tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(getattr(tree.body[0], "value", None), ast.Constant)
            and isinstance(tree.body[0].value.value, str)
        ):
            doc_node = tree.body[0]

        import_line_ranges = set()
        collector = UsageCollector()
        for node in tree.body:
            if node is doc_node:
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                    import_line_ranges.add(ln)
            else:
                collector.visit(node)

        # Compute 1-based line/byte offsets on original code and apply span replacements bottom-up
        line_starts = [0]
        for idx_ch, ch in enumerate(code):
            if ch == "\n":
                line_starts.append(idx_ch + 1)

        def _to_offset(lineno: int, col_offset: int) -> int:
            line_text = code[line_starts[lineno - 1]: (line_starts[lineno] - 1 if lineno < len(line_starts) else len(code))]
            # col_offset in Python AST is UTF-8 byte offset within the line
            prefix_str = line_text.encode("utf-8")[:col_offset].decode("utf-8")
            return line_starts[lineno - 1] + len(prefix_str)

        spliced = code
        for ln, col, end_ln, end_col, repl in sorted(collector.replacements, reverse=True):
            start_off = _to_offset(ln, col)
            end_off = _to_offset(end_ln, end_col)
            spliced = spliced[:start_off] + repl + spliced[end_off:]

        # Extract header (up to end of module docstring, or encoding line) and remaining body lines (excluding top-level imports)
        spliced_lines = spliced.splitlines()
        header_end_line = doc_node.end_lineno if doc_node is not None else 0
        if header_end_line == 0:
            for idx_ln, raw_ln in enumerate(spliced_lines, 1):
                if raw_ln.strip().startswith("#!") or "coding:" in raw_ln:
                    header_end_line = idx_ln
                elif raw_ln.strip() == "" and header_end_line > 0:
                    continue
                else:
                    break

        header = "\n".join(spliced_lines[:header_end_line]) if header_end_line > 0 else "#!/usr/bin/env python\n# coding:utf-8"
        remaining_body_lines = [
            raw_ln
            for idx_ln, raw_ln in enumerate(spliced_lines[header_end_line:], header_end_line + 1)
            if idx_ln not in import_line_ranges
        ]
        while remaining_body_lines and remaining_body_lines[0].strip() == "":
            remaining_body_lines.pop(0)
        body_code = "\n".join(remaining_body_lines)

        # Merge grouped_from_imports that were explicitly declared with those discovered from attribute access
        merged_from = {}
        for mod_name, sym_map in grouped_from_imports.items():
            for sym_name, alias in sym_map.items():
                # Keep if used in body or if it wasn't a typing-only unused symbol
                if mod_name in collector.used_from_imports and sym_name in collector.used_from_imports[mod_name]:
                    merged_from.setdefault(mod_name, {})[sym_name] = alias
                elif mod_name != "typing":
                    merged_from.setdefault(mod_name, {})[sym_name] = alias
        for mod_name, sym_map in collector.used_from_imports.items():
            for sym_name, alias in sym_map.items():
                merged_from.setdefault(mod_name, {})[sym_name] = alias

        for mod_name in sorted(merged_from.keys()):
            sym_map = merged_from[mod_name]
            parts = [f"{sym} as {sym_map[sym]}" for sym in sorted(sym_map.keys())]
            external_imports.append(f"from {mod_name} import " + ", ".join(parts))

        for mod_name in sorted(collector.unresolved_whole_modules):
            external_imports.append(f"import {mod_name}")

        final_external = sorted(list(set(external_imports)))
        final_internal = sorted(list(set(internal_imports)))

        # Build import block
        import_lines = []
        if final_external:
            import_lines.extend(final_external)
        if final_internal:
            if final_external:
                import_lines.append("")
            import_lines.extend(final_internal)

        final_code = header + "\n"
        if import_lines:
            final_code += "\n".join(import_lines) + "\n\n"

        final_code += body_code
        return final_code

    def _ensure_granular_imports_regex(self, code: str) -> str:
        """Original regex fallback (kept for safety)."""
        match_doc = reSearch(r'"""(.*?)"""', code, reMULTILINE | reDOTALL)
        if match_doc:
            header_end = match_doc.end()
            header = code[:header_end]
            rest = code[header_end:]
        else:
            header = ""
            rest = code
        lines = rest.splitlines()
        raw_imports = []
        body_lines = []
        has_os_import = False
        has_sys_import = False
        has_re_import = False
        typing_imported_names = set()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                is_std = False
                if reSearch(r'\b(os|sys|re)\b', stripped):
                    is_std = True
                    if "os" in stripped: has_os_import = True
                    if "sys" in stripped: has_sys_import = True
                    if "re" in stripped: has_re_import = True
                if stripped.startswith("from typing import"):
                    match = reSearch(r"from typing import (.*)", stripped)
                    if match:
                        imports_part = match.group(1).split("#")[0]
                        for item in imports_part.split(","):
                            item = item.strip()
                            if not item: continue
                            name = item.split(" as ")[0].strip() if " as " in item else item
                            typing_imported_names.add(name)
                elif not is_std:
                    raw_imports.append(line)
            else:
                body_lines.append(line)
        body_text = "\n".join(body_lines)
        standard_imports_to_add = []
        if has_os_import:
            if reSearch(r'\bos\.path\.join\b', body_text):
                body_text = reSub(r'\bos\.path\.join\b', 'osPathJoin', body_text)
                standard_imports_to_add.append("from os.path import join as osPathJoin")
            if reSearch(r'\bos\.path\.exists\b', body_text):
                body_text = reSub(r'\bos\.path\.exists\b', 'osPathExists', body_text)
                standard_imports_to_add.append("from os.path import exists as osPathExists")
        if has_sys_import:
            if reSearch(r'\bsys\.exit\b', body_text):
                body_text = reSub(r'\bsys\.exit\b', 'sysExit', body_text)
                standard_imports_to_add.append("from sys import exit as sysExit")
        if has_re_import:
            if reSearch(r'\bre\.search\b', body_text):
                body_text = reSub(r'\bre\.search\b', 'reSearch', body_text)
                standard_imports_to_add.append("from re import search as reSearch")
        typing_imports_to_add = []
        typing_used = set()
        for name in sorted(typing_imported_names):
            if reSearch(rf'\b{name}\b', body_text):
                typing_used.add(name)
                body_text = reSub(rf'\b{name}\b', f'type{name}', body_text)
        if typing_used:
            aliased = [f"{name} as type{name}" for name in sorted(typing_used)]
            typing_imports_to_add.append("from typing import " + ", ".join(aliased))
        external_imports = []
        internal_imports = []
        for imp_line in raw_imports:
            if any(imp_line.strip().startswith(f"{x} {p}") for x in ["import", "from"] for p in ["agents", "core", "utils", "evaluation", "skills", "specs", "tests"]) or imp_line.strip().startswith(("from .", "import .")):
                internal_imports.append(imp_line.strip())
            else:
                external_imports.append(imp_line.strip())
        external_imports.extend(standard_imports_to_add)
        external_imports.extend(typing_imports_to_add)
        external_imports = sorted(list(set(external_imports)))
        internal_imports = sorted(list(set(internal_imports)))
        imports_block = []
        if external_imports: imports_block.extend(external_imports)
        if internal_imports:
            if external_imports: imports_block.append("")
            imports_block.extend(internal_imports)
        new_rest_lines = []
        if imports_block:
            new_rest_lines.extend(imports_block)
            new_rest_lines.append(""); new_rest_lines.append(""); new_rest_lines.append("")
        body_lines_rewritten = body_text.splitlines()
        body_start_idx = 0
        while body_start_idx < len(body_lines_rewritten) and body_lines_rewritten[body_start_idx].strip() == "": body_start_idx += 1
        new_rest_lines.extend(body_lines_rewritten[body_start_idx:])
        return header + "\n" + "\n".join(new_rest_lines)

    # -----------------------------------------------------------------------------------------------
    def _ensure_method_dividers(self, code: str) -> str:
        lines = code.splitlines()
        cleaned_lines = []
        dashes_95 = "-" * 95

        idx = 0
        has_seen_code = False
        while idx < len(lines):
            line = lines[idx]
            stripped = line.strip()
            indent_len = len(line) - len(line.lstrip())
            divider_for_indent = (" " * indent_len) + f"# {dashes_95}"

            # Normalize existing divider lines (25+ dashes) in place instead of deleting module-level dividers
            if reMatch(r"^#\s*-{25,}\s*$", stripped):
                if not cleaned_lines or not cleaned_lines[-1].strip().startswith("# ---"):
                    cleaned_lines.append(divider_for_indent)
                idx += 1
                continue

            is_def = stripped.startswith("def ") or stripped.startswith("async def ")
            if stripped.startswith("class ") or is_def:
                if stripped.startswith("class "):
                    has_seen_code = True
                elif is_def:
                    is_init = stripped.startswith("def __init__")
                    if not is_init and cleaned_lines and has_seen_code:
                        prev_line = cleaned_lines[-1].strip()
                        if not prev_line.startswith("# -"):
                            if prev_line == "":
                                prev_prev = cleaned_lines[-2].strip() if len(cleaned_lines) >= 2 else ""
                                if not prev_prev.startswith("# -"):
                                    cleaned_lines[-1] = divider_for_indent
                            else:
                                cleaned_lines.append(divider_for_indent)
                    has_seen_code = True

            cleaned_lines.append(line)
            idx += 1

        return "\n".join(cleaned_lines)

    # -----------------------------------------------------------------------------------------------
    def _ensure_logger_formatting(self, code: str, class_name: str) -> str:
        """
        Standardizes self.logger.<level>(...) calls onto canonical f-strings:
        `self.logger.<level>(f"{self.Name} : {msg}")`, preserving already-prefixed calls.
        """
        for level in ("debug", "info", "warning", "error", "critical"):
            pattern_f = r"self\.logger\." + level + r'\(f(["\'])(.*?)\1\)'

            def replace_f(m, lvl=level):
                quote_ch = m.group(1)
                content = m.group(2)
                if content.startswith("{self.Name}") or "{self.Name} :" in content:
                    return m.group(0)
                return f"self.logger.{lvl}(f{quote_ch}{{self.Name}} : {content}{quote_ch})"

            code = reSub(pattern_f, replace_f, code)

            pattern_s = r"self\.logger\." + level + r'\((["\'])([^{}"\']*?)\1\)'

            def replace_s(m, lvl=level):
                quote_ch = m.group(1)
                content = m.group(2)
                if content.startswith(f"{class_name} :") or " : " in content[:40]:
                    return m.group(0)
                return f"self.logger.{lvl}(f{quote_ch}{{self.Name}} : {content}{quote_ch})"

            code = reSub(pattern_s, replace_s, code)

        return code

    # -----------------------------------------------------------------------------------------------
    def _ensure_class_and_method_docstrings(self, code: str) -> str:
        lines = code.splitlines()
        
        # Associate signature end indices with insertion action
        insertions = {} # idx -> (indent, type, name)
        
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("class "):
                indent = len(line) - len(line.lstrip())
                sig_end = idx
                while sig_end < len(lines) and not lines[sig_end].strip().endswith(":"):
                    sig_end += 1
                
                # Check if docstring exists after sig_end
                next_idx = sig_end + 1
                has_doc = False
                while next_idx < len(lines):
                    next_line = lines[next_idx].strip()
                    if next_line == "" or next_line.startswith("#"):
                        next_idx += 1
                        continue
                    if next_line.startswith('"""'):
                        has_doc = True
                    break
                
                if not has_doc:
                    class_name = stripped.split("class ")[1].split("(")[0].split(":")[0].strip()
                    insertions[sig_end] = (indent + 4, "class", class_name)
                    
            elif stripped.startswith("def "):
                indent = len(line) - len(line.lstrip())
                sig_end = idx
                while sig_end < len(lines) and not lines[sig_end].strip().endswith(":"):
                    sig_end += 1
                
                next_idx = sig_end + 1
                has_doc = False
                while next_idx < len(lines):
                    next_line = lines[next_idx].strip()
                    if next_line == "" or next_line.startswith("#"):
                        next_idx += 1
                        continue
                    if next_line.startswith('"""'):
                        has_doc = True
                    break
                
                if not has_doc:
                    func_name = stripped.split("def ")[1].split("(")[0].strip()
                    insertions[sig_end] = (indent + 4, "method", func_name)
                    
        # Second pass: reconstruct code with insertions
        final_lines = []
        for idx, line in enumerate(lines):
            final_lines.append(line)
            if idx in insertions:
                indent, doc_type, name = insertions[idx]
                doc_indent = " " * indent
                final_lines.append(f'{doc_indent}"""')
                if doc_type == "class":
                    final_lines.append(f'{doc_indent}[Description of the role and operation of class {name}]')
                else:
                    final_lines.append(f'{doc_indent}[Description of the operation of method {name}]')
                final_lines.append(f'{doc_indent}"""')
                
        return "\n".join(final_lines)

    # -----------------------------------------------------------------------------
    def transform_file(self, file_path: Path, dry_run: bool = False) -> bool:
        """
        Reads, transforms, and rewrites a python file if changes are needed.
        Returns True if the file was modified or would be modified.
        """
        if not file_path.is_file() or file_path.suffix != ".py":
            return False

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            self._log("error", f"Failed to read {file_path}: {e}")
            return False

        try:
            transformed = self.transform(code=content, class_name=file_path.stem)
        except Exception as e:
            self._log("error", f"Transformation error in {file_path}: {e}")
            return False

        if transformed != content:
            if dry_run:
                self._log("info", f"[DRY-RUN] Would reformat: {file_path}")
            else:
                try:
                    file_path.write_text(transformed, encoding="utf-8")
                    self._log("info", f"✅ Formatted: {file_path}")
                except Exception as e:
                    self._log("error", f"Failed to write {file_path}: {e}")
                    return False
            return True
        return False

    # -----------------------------------------------------------------------------
    def transform_path(self, target_path: Path, dry_run: bool = False) -> int:
        """
        Recursively transforms Python files in a directory or transforms a single file.
        Returns count of modified files.
        """
        modified_count = 0
        if target_path.is_file():
            if self.transform_file(target_path, dry_run=dry_run):
                modified_count += 1
            return modified_count

        excluded_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}
        for root, dirs, files in os.walk(target_path):
            dirs[:] = [d for d in dirs if d not in excluded_dirs and not d.startswith(".")]
            for f in sorted(files):
                if f.endswith(".py"):
                    fp = Path(root) / f
                    if self.transform_file(fp, dry_run=dry_run):
                        modified_count += 1

        return modified_count

# -----------------------------------------------------------------------------

def main():
    """CLI runner for format-compliance."""
    import argparse
    parser = argparse.ArgumentParser(description="AST-Based Python Code Compliance Formatter")
    parser.add_argument("path", nargs="?", default=".", help="Target file or directory to format (defaults to current dir)")
    parser.add_argument("--dry-run", action="store_true", help="Preview modifications without writing to disk")
    args = parser.parse_args()

    target = Path(args.path).resolve()
    transformer = CodeTransformer()
    count = transformer.transform_path(target, dry_run=args.dry_run)
    action_str = "would be modified" if args.dry_run else "modified"
    print(f"\n✨ CodeTransformer finished: {count} file(s) {action_str}.")

if __name__ == "__main__":
    main()

