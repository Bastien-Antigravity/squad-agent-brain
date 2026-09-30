---
microservice: obsidian-brain
type: documentation
status: active
tags:
- '#service/obsidian-brain'
- '#type/documentation'
- '#state/active'
- '#zone/3-fleet'
---
# 🤝 Contributing to 08-Base-Scripts

Welcome to the **Engine Room** of the Bastien-Antigravity AI Squad and Knowledge Management System.

Follow these guidelines when adding new automation scripts, commands, or AI client wrappers to this codebase.

---

## 🛠️ Adding a New CLI Command

All CLI command modules are stored in the [src/commands/](src/commands) directory.

### 1. Implementation Checklist
- **Shebang & UTF-8**: Start the file with:
  ```python
  #!/usr/bin/env python
  # coding:utf-8
  ```
- **Triple-Block Header**: Include the mandatory module docstring:
  ```python
  """
  ESSENTIAL PROCESS:
  [Description of what the command does]
  
  DATA FLOW:
  1. [Step 1: Input]
  2. [Step 2: Core Processing]
  3. [Step 3: Output]
  
  KEY PARAMETERS:
  - [param]: [description]
  """
  ```
- **DRY Bootstrapping**: Import and run the standard virtualenv bootstrap logic:
  ```python
  from pathlib import Path
  from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths
  
  script_dir = Path(__file__).resolve().parent
  vault_root_path = ensure_virtualenv(str(script_dir))
  prepend_venv_bin(vault_root_path)
  ensure_import_paths(script_dir, vault_root_path)
  ```
- **Logging & Config**: Load the ecosystem configuration and UniLog logger using the library layer:
  ```python
  from lib.orchestration_lib import get_logger, get_config
  config = get_config()
  logger = get_logger("MyCommandName")
  ```
- **Entrypoint**: Wrap the execution in a parameter-less `def main():` function and add a standard execution guard:
  ```python
  def main():
      # Your logic here
      pass
      
  if __name__ == '__main__':
      main()
  ```

### 2. Router Integration
Add your new command to the `COMMANDS_MAP` dictionary in [main.py](main.py):
```python
COMMANDS_MAP = {
    # ...
    "my-new-command": "my_new_command"
}
```

---

## 🤖 Adding a New AI Client Wrapper

AI client wrappers are stored inside the [src/clients/](src/clients) directory.

1. Implement the client's API connection and session management logic.
2. Register the client inside the `CLIENTS` mapping in `registry.py` to make it accessible to `start-squad`.
