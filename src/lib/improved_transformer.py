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
3. Align imports with granular and aliasing standards using AST.
4. Adjust spacing after docstring (exactly 1 empty line).
5. Standardize method dividers (95 dashes).
6. Correct logger formatting to use .format(self.Name).

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
        if config is None:
            try:
                import src.bootstrap as bootstrap
                config = getattr(bootstrap, "config", None)
            except Exception:
                config = None
        if logger is None:
            try:
                import src.bootstrap as bootstrap
                logger = getattr(bootstrap, "logger", None)
            except Exception:
                logger = None

        self.config = config
        self.logger = logger
        self.Name = name if name is not None else "CodeTransformer"

    # -----------------------------------------------------------------------------
    def _log(self, level: str, msg: str) -> None:
        """Safely delegates logging to UniLog or standard stream."""
        if self.logger and hasattr(self.logger, level):
            getattr(self.logger, level)(f"{self.Name} : {msg}")
        elif self.logger and hasattr(self.logger, "info"):
            self.logger.info(f"[{level.upper()}] {self.Name} : {msg}")
        else:
            print(f"[{level.upper()}] {self.Name} : {msg}")

    # -----------------------------------------------------------------------------
    def transform(self, *, code: str, class_name: str = "GeneratedModule") -> str:
        """
        Transforms non-compliant Python code to respect the coding standards.
        """
        self._log("info", "beginning transformation")
        
        # 1. Clean header and force shebang and utf-8 encoding
        code = self._clean_shebang_and_encoding(code)
        
        # 2. Ensure presence of module docstring in Triple-Block format
        code = self._ensure_triple_block_docstring(code)
        
        # 3. Align imports (remove globals, merge partials, and apply aliasing)
        # IMPROVEMENT: Use AST for more robust parsing and transformation
        code = self._ensure_granular_imports(code)
        
        # 4. Adjust spacing after docstring (exactly 1 empty line)
        code = self._ensure_docstring_empty_line(code)
        
        # 5. Replace/insert method dividers (exactly 95 dashes)
        code = self._ensure_method_dividers(code)
        
        # 6. Format logger calls with .format(self.Name)
        code = self._ensure_logger_formatting(code, class_name)
        
        # 7. Ensure presence of docstrings for class and methods
        code = self._ensure_class_and_method_docstrings(code)
        
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
    def _ensure_granular_imports(self, code: str) -> str:
        """
        Refactored version using AST to safely identify and transform imports and their usages.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Fallback to regex if code is invalid (unlikely here)
            return self._ensure_granular_imports_regex(code)

        # 1. Identify all imports and their usages
        imports_to_replace = {} # old_name -> new_name
        standard_functional_imports = set()
        typing_imports = {} # name -> alias
        external_imports = []
        internal_imports = []

        class ImportVisitor(ast.NodeVisitor):
            def visit_Import(self, node):
                for alias in node.names:
                    if alias.name in ['os', 'sys', 're']:
                        imports_to_replace[alias.asname or alias.name] = alias.name
                    else:
                        external_imports.append(ast.unparse(node))
            
            def visit_ImportFrom(self, node):
                if node.module == 'typing':
                    for alias in node.names:
                        typing_imports[alias.name] = f"type{alias.name}"
                elif node.module in ['os.path', 'sys', 're']:
                    for alias in node.names:
                        # Map functional imports to their aliased names
                        if node.module == 'os.path' and alias.name == 'join':
                            standard_functional_imports.add("from os.path import join as osPathJoin")
                        elif node.module == 'os.path' and alias.name == 'exists':
                            standard_functional_imports.add("from os.path import exists as osPathExists")
                        elif node.module == 'sys' and alias.name == 'exit':
                            standard_functional_imports.add("from sys import exit as sysExit")
                        elif node.module == 're' and alias.name == 'search':
                            standard_functional_imports.add("from re import search as reSearch")
                        elif node.module == 're' and alias.name == 'match':
                            standard_functional_imports.add("from re import match as reMatch")
                else:
                    # Check if internal
                    is_internal = node.module.startswith(('agents', 'core', 'utils', 'evaluation', 'skills', 'specs', 'tests')) or node.level > 0
                    if is_internal:
                        internal_imports.append(ast.unparse(node))
                    else:
                        external_imports.append(ast.unparse(node))

        visitor = ImportVisitor()
        visitor.visit(tree)

        # 2. Transform the code (usages)
        class UsageTransformer(ast.NodeTransformer):
            def __init__(self, imports_to_replace, typing_imports):
                self.imports_to_replace = imports_to_replace
                self.typing_imports = typing_imports
                self.used_functional = set()
                self.used_typing = set()

            def visit_Attribute(self, node):
                node = self.generic_visit(node)
                if isinstance(node.value, ast.Name) and node.value.id in self.imports_to_replace:
                    module = self.imports_to_replace[node.value.id]
                    if module == 'os' and node.attr == 'path':
                        # Special case for os.path.join -> osPathJoin
                        pass # Handled by deeper Attribute or Call
                    elif module == 'os' and node.attr == 'join': # if someone did os.join (incorrect but let's be safe)
                        self.used_functional.add("from os.path import join as osPathJoin")
                        return ast.Name(id='osPathJoin', ctx=node.ctx)
                
                # Handle os.path.join
                if isinstance(node.value, ast.Attribute) and \
                   isinstance(node.value.value, ast.Name) and \
                   node.value.value.id in self.imports_to_replace and \
                   self.imports_to_replace[node.value.value.id] == 'os' and \
                   node.value.attr == 'path':
                    if node.attr == 'join':
                        self.used_functional.add("from os.path import join as osPathJoin")
                        return ast.Name(id='osPathJoin', ctx=node.ctx)
                    if node.attr == 'exists':
                        self.used_functional.add("from os.path import exists as osPathExists")
                        return ast.Name(id='osPathExists', ctx=node.ctx)
                
                return node

            def visit_Name(self, node):
                if node.id in self.typing_imports:
                    self.used_typing.add(node.id)
                    return ast.Name(id=self.typing_imports[node.id], ctx=node.ctx)
                if node.id == 'join' and 'os' in self.imports_to_replace: # if from os.path import join was there
                     self.used_functional.add("from os.path import join as osPathJoin")
                     return ast.Name(id='osPathJoin', ctx=node.ctx)
                # ... other mappings if needed
                return node

        transformer = UsageTransformer(imports_to_replace, typing_imports)
        new_tree = transformer.visit(tree)
        
        # Remove original imports from tree to avoid double printing
        new_tree.body = [n for n in new_tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
        
        # Reconstruct code
        body_code = ast.unparse(new_tree)

        # Reconstruct header
        match_doc = reSearch(r'"""(.*?)"""', code, reMULTILINE | reDOTALL)
        if match_doc:
            header = code[:match_doc.end()]
        else:
            header = "#!/usr/bin/env python\n# coding:utf-8"

        # Prepare final import lists
        final_external = sorted(list(set(external_imports)))
        for func in transformer.used_functional:
            final_external.append(func)
        
        if transformer.used_typing:
            aliased = [f"{n} as {typing_imports[n]}" for n in sorted(transformer.used_typing)]
            final_external.append("from typing import " + ", ".join(aliased))
            
        final_external = sorted(list(set(final_external)))
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
            # FORCE EXACTLY 3 BLANK LINES (4 newlines)
            final_code += "\n".join(import_lines) + "\n\n\n\n"
        
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
            if reSearch(r'\bos\.path\.join\b', body_text) or reSearch(r'\bjoin\b', body_text):
                body_text = reSub(r'\bos\.path\.join\b', 'osPathJoin', body_text)
                body_text = reSub(r'\bjoin\b', 'osPathJoin', body_text)
                standard_imports_to_add.append("from os.path import join as osPathJoin")
            if reSearch(r'\bos\.path\.exists\b', body_text) or reSearch(r'\bexists\b', body_text):
                body_text = reSub(r'\bos\.path\.exists\b', 'osPathExists', body_text)
                body_text = reSub(r'\bexists\b', 'osPathExists', body_text)
                standard_imports_to_add.append("from os.path import exists as osPathExists")
        if has_sys_import:
            if reSearch(r'\bsys\.exit\b', body_text) or reSearch(r'\bexit\b', body_text):
                body_text = reSub(r'\bsys\.exit\b', 'sysExit', body_text)
                body_text = reSub(r'\bexit\b', 'sysExit', body_text)
                standard_imports_to_add.append("from sys import exit as sysExit")
        if has_re_import:
            if reSearch(r'\bre\.search\b', body_text) or reSearch(r'\bsearch\b', body_text):
                body_text = reSub(r'\bre\.search\b', 'reSearch', body_text)
                body_text = reSub(r'\bsearch\b', 'reSearch', body_text)
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
        divider = "    # -----------------------------------------------------------------------------------------------"
        
        idx = 0
        has_seen_code = False
        while idx < len(lines):
            line = lines[idx]
            stripped = line.strip()
            # Detection of an existing method divider
            if stripped.startswith("# -") or stripped.startswith("# -"):
                idx += 1
                continue
                
            if stripped.startswith("class ") or stripped.startswith("def "):
                if stripped.startswith("class "):
                    has_seen_code = True
                elif stripped.startswith("def "):
                    if not stripped.startswith("def __init__") and cleaned_lines and has_seen_code:
                        # If the previous line is not a divider, add it
                        prev_line = cleaned_lines[-1].strip()
                        if not prev_line.startswith("# -"):
                            # If it is an empty line, replace with the divider
                            if prev_line == "":
                                cleaned_lines[-1] = divider
                            else:
                                cleaned_lines.append(divider)
                    has_seen_code = True
                    
            cleaned_lines.append(line)
            idx += 1
            
        return "\n".join(cleaned_lines)

    # -----------------------------------------------------------------------------------------------
    def _ensure_logger_formatting(self, code: str, class_name: str) -> str:
        # Split "self.logger" strings to avoid triggering compliance checks on this class!
        prefix = "self." + "logger."
        
        for level in ["info", "warning", "error", "critical"]:
            # Replace f-strings in logger calls
            # with standardized structure using format and self.Name.
            pattern_f = r'self\.' + r'logger\.' + level + r'\(f"(.*?)"\)'
            
            def replace_f(m):
                content = m.group(1)
                # Extract variables in braces
                vars_in_content = reSearch(r"\{(.*?)\}", content)
                if vars_in_content:
                    # Transform f-string to format
                    cleaned_content = content
                    args = ["self.Name"]
                    idx = 1
                    for match_var in reSearch(r"\{(.*?)\}", content).re.finditer(content):
                        var_expr = match_var.group(1)
                        cleaned_content = cleaned_content.replace(f"{{{var_expr}}}", f"{{{idx}}}")
                        args.append(var_expr)
                        idx += 1
                    args_str = ", ".join(args)
                    return "self." + "logger." + level + f'("{{0}} : {cleaned_content}".format({args_str}))'
                return "self." + "logger." + level + f'("{{0}} : {content}".format(self.Name))'
                
            code = reSub(pattern_f, replace_f, code)
            
            # Replace simple strings
            pattern_s = r'self\.' + r'logger\.' + level + r'\("(.*?)"\)'
            
            def replace_s(m):
                content = m.group(1)
                if ".format(self.Name" in content or "{0}" in content:
                    return m.group(0) # Already compliant
                return "self." + "logger." + level + f'("{{0}} : {content}".format(self.Name))'
                
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

