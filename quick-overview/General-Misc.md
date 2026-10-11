---
microservice: base-scripts
type: overview
status: active
tags:
- '#service/base-scripts'
- '#type/overview'
- '#state/active'
- '#zone/3-fleet'
- '#ai/ignore'
---
# 📌 General & Miscellaneous: base-scripts

## Virtual Environment
Dependencies are isolated in `.venv`. The bootstrapper in `src/bootstrap/__init__.py` automatically sets up `sys.path` to include `microservice-toolbox/python`.

## Database Isolation
When running daemon or stateful operations, the database connection pool uses `obsidiandb` and isolates table schemas under `"08-Base-Scripts"`.

## Ports Allocation
- **8085**: HTTP REST & OpenMFE Web UI
- **8087**: gRPC SquadControl Service
