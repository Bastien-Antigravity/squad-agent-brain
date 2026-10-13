---
microservice: base-scripts
type: playbook
status: active
tags:
- '#service/base-scripts'
- '#type/playbook'
- '#state/active'
- '#zone/3-fleet'
- '#ai/ignore'
---
# 🧪 Testing Playbook: squad-agent

## Running Unit Tests
```bash
# Execute full pytest suite inside the virtual environment
.venv/bin/python -m pytest tests/

# Run specific test file
.venv/bin/python -m pytest tests/test_scaffold_microservice.py

# Run with verbose output
.venv/bin/python -m pytest -v tests/
```

## Running Operational Verifications
```bash
# Verify code compliance
python3 main.py validate-compliance src/

# Run preflight check
python3 main.py preflight-check

# Audit port drift
python3 main.py audit-ports
```
