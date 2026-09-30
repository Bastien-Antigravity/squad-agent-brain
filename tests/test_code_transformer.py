#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for CodeTransformer (AST-based code refactoring and compliance engine).

DATA FLOW:
1. Feeds unformatted, non-compliant Python source strings to CodeTransformer.
2. Asserts headers, Triple-Block docstring, section dividers, and AST import alignments.
3. Tests transform_file dry-run and in-place write mechanisms.

KEY PARAMETERS:
- TestCodeTransformer: TestCase class verifying CodeTransformer capabilities.
"""

import unittest
import tempfile
import sys
from pathlib import Path

# Add 08-Base-Scripts to sys.path
_self_dir = Path(__file__).resolve().parent.parent
if str(_self_dir) not in sys.path:
    sys.path.insert(0, str(_self_dir))

import src.bootstrap as bootstrap
from src.lib.improved_transformer import CodeTransformer

# -----------------------------------------------------------------------------

class TestCodeTransformer(unittest.TestCase):
    def setUp(self):
        self.transformer = CodeTransformer(
            config=bootstrap.config,
            logger=bootstrap.logger,
            name="TestTransformer"
        )

    def test_shebang_and_encoding_injection(self):
        raw_code = "x = 42\nprint(x)\n"
        result = self.transformer._clean_shebang_and_encoding(raw_code)
        self.assertTrue(result.startswith("#!/usr/bin/env python\n# coding:utf-8\n"))

    def test_triple_block_docstring_injection(self):
        raw_code = "#!/usr/bin/env python\n# coding:utf-8\n\nx = 1\n"
        result = self.transformer._ensure_triple_block_docstring(raw_code)
        self.assertIn("ESSENTIAL PROCESS:", result)
        self.assertIn("DATA FLOW:", result)
        self.assertIn("KEY PARAMETERS:", result)

    def test_method_dividers_insertion(self):
        raw_code = (
            "class MyService:\n"
            "    def method_one(self):\n"
            "        pass\n"
            "    def method_two(self):\n"
            "        pass\n"
        )
        result = self.transformer._ensure_method_dividers(raw_code)
        self.assertIn("# -----------------------------------------------------------------------------------------------", result)

    def test_full_transform_end_to_end(self):
        raw_code = (
            "import os\n"
            "import sys\n\n"
            "class SampleClass:\n"
            "    def run(self):\n"
            "        self.logger.info('running sample')\n"
        )
        transformed = self.transformer.transform(code=raw_code, class_name="SampleClass")
        self.assertTrue(transformed.startswith("#!/usr/bin/env python\n# coding:utf-8\n"))
        self.assertIn("ESSENTIAL PROCESS:", transformed)
        self.assertIn("DATA FLOW:", transformed)
        self.assertIn("KEY PARAMETERS:", transformed)
        self.assertIn("# -----------------------------------------------------------------------------------------------", transformed)

    def test_transform_file_dry_run_and_in_place(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test_module.py"
            file_path.write_text("x = 100\n", encoding="utf-8")

            # 1. Dry run: should return True without modifying file on disk
            modified = self.transformer.transform_file(file_path, dry_run=True)
            self.assertTrue(modified)
            self.assertEqual(file_path.read_text(encoding="utf-8"), "x = 100\n")

            # 2. In-place run: should modify file on disk
            modified = self.transformer.transform_file(file_path, dry_run=False)
            self.assertTrue(modified)
            updated_content = file_path.read_text(encoding="utf-8")
            self.assertTrue(updated_content.startswith("#!/usr/bin/env python\n# coding:utf-8\n"))

if __name__ == "__main__":
    unittest.main()
