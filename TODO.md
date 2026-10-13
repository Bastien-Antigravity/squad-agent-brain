---
microservice: squad-agent
type: task
status: active
tags:
- '#service/squad-agent'
- '#type/task'
- '#state/active'
- '#zone/3-fleet'
---

# 📝 TODO: squad-agent

- [x] Implement central CLI command router in `main.py`
- [x] Implement 4-layer port drift verification engine (`audit-ports`)
- [x] Implement mechanical code compliance auditor (`validate-compliance`)
- [x] Implement OpenMFE dashboard on port 8085 with dynamic auto-registration to web-interface (port 5000)
- [x] Add gRPC SquadControl service on port 8087
- [x] Add dynamic Telegram management interface
- [x] Integrate PostgreSQL memory store with schema isolation (`08-Squad-Agent`)
- [ ] Add end-to-end integration tests in `sandbox-testing`
- [ ] Implement NATS JetStream event publishing for fleet state mutations
