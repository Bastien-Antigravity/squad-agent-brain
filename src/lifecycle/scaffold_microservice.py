#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Scaffolds a new Bastien-Antigravity microservice adhering to canonical repository
structure, mandatory root files, Docker standards, and BDD specifications.

DATA FLOW:
1. Input: Service name, target language (Go/Python/Rust/C++), port, description.
2. Logic: Generates folder architecture, OpenMFE Exchange Contracts, creates the
   12 mandatory root files & folders, establishes standalone.yaml symlink, and
   generates BDD specs in 02-Business-BDD.
3. Output: Production-ready microservice directory and ecosystem registration snippets.

KEY PARAMETERS:
- --name: Name of the microservice (kebab-case, e.g., market-observer).
- --lang: Target language ('go', 'python', 'rust', 'cpp'). Defaults to 'go'.
- --port: Primary service port (e.g., 8090).
- --dest: Target directory path (defaults to workspace root / <name>).
- --dry-run: Preview file fabrication without writing to disk.
"""

import argparse
import os
import sys
from pathlib import Path

# -----------------------------------------------------------------------------

def resolve_workspace_root() -> Path:
    """Resolves the Bastien-Antigravity workspace root dynamically."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "docker-deployment").exists() and (parent / "microservice-toolbox").exists():
            return parent
        if (parent / "Bastien-Antigravity" / "docker-deployment").exists():
            return parent / "Bastien-Antigravity"
        try:
            for s in parent.iterdir():
                if s.is_dir() and (s / "docker-deployment").exists() and (s / "microservice-toolbox").exists():
                    return s
        except Exception:
            pass
    return Path.cwd()

# -----------------------------------------------------------------------------

def create_file(path: Path, content: str, dry_run: bool = False) -> None:
    """Creates a file with parent directory creation, respecting dry-run mode."""
    if dry_run:
        print(f"  [DRY-RUN] Would create file: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✅ Created: {path}")

# -----------------------------------------------------------------------------

def create_symlink(target_path: Path, link_target: str, dry_run: bool = False) -> None:
    """Creates a symbolic link, respecting dry-run mode."""
    if dry_run:
        print(f"  [DRY-RUN] Would symlink: {target_path} -> {link_target}")
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.is_symlink() or target_path.exists():
        target_path.unlink()
    os.symlink(link_target, target_path)
    print(f"  🔗 Symlinked: {target_path} -> {link_target}")

# -----------------------------------------------------------------------------

def _to_pascal_case(name: str) -> str:
    """Converts a kebab/snake identifier into PascalCase."""
    return "".join(part.capitalize() for part in name.replace("_", "-").split("-") if part)

# -----------------------------------------------------------------------------

def generate_openmfe_component_js(name: str, cap_name: str, desc: str) -> str:
    """Generates a standardized BastienMFEElement Web Component with dynamic Exchange Contract tabs."""
    class_name = _to_pascal_case(name) + "MFE"
    tag_name = f"{name}-mfe"
    tabs_id = f"{cap_name}-tabs-bar"
    panels_id = f"{cap_name}-panels-host"
    return f"""// ============================================================================
// Standardized OpenMFE Web Component for {name}
// Consumes authoritative Exchange Contracts from GET /api/v1/contracts via BastienMFEContracts.
// ============================================================================

class {class_name} extends (window.BastienMFEElement || HTMLElement) {{
    render() {{
        this.innerHTML = `
            <div class="openmfe-container">
                <div class="openmfe-kpi-grid">
                    <div class="openmfe-kpi-card">
                        <span class="openmfe-kpi-label"><i class="fa fa-heartbeat"></i> Status</span>
                        <span class="openmfe-kpi-val" id="{cap_name}-kpi-status">Checking...</span>
                        <span class="openmfe-kpi-sub">{desc}</span>
                    </div>
                    <div class="openmfe-kpi-card">
                        <span class="openmfe-kpi-label"><i class="fa fa-tag"></i> Version</span>
                        <span class="openmfe-kpi-val" id="{cap_name}-kpi-version">—</span>
                        <span class="openmfe-kpi-sub">VERSION.txt</span>
                    </div>
                    <div class="openmfe-kpi-card">
                        <span class="openmfe-kpi-label"><i class="fa fa-exchange"></i> Exchange Contracts</span>
                        <span class="openmfe-kpi-val" id="{cap_name}-kpi-contracts">—</span>
                        <span class="openmfe-kpi-sub">Authoritative Service Introspection</span>
                    </div>
                </div>

                <div class="openmfe-tabs-bar" id="{tabs_id}" role="tablist">
                    <button type="button" class="openmfe-tab-btn is-active" data-tab="overview" role="tab">
                        <i class="fa fa-tachometer"></i> Live Overview
                    </button>
                </div>

                <div id="{panels_id}">
                    <div class="openmfe-panel is-active" id="panel-overview">
                        <div class="openmfe-card">
                            <div class="openmfe-card__header">
                                <h4 class="openmfe-card__title"><i class="fa fa-sliders"></i> {name} Live Operations</h4>
                                <button type="button" class="openmfe-btn openmfe-btn--sm" id="{cap_name}-btn-refresh">
                                    <i class="fa fa-refresh"></i> Refresh
                                </button>
                            </div>
                            <div class="openmfe-card__body" id="{cap_name}-overview-body">
                                <p class="openmfe-text-muted"><i class="fa fa-spinner fa-spin"></i> Loading service telemetry...</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }}

    cacheDom() {{
        this.activeTab = this.activeTab || 'overview';
        this.dom = {{
            kpiStatus: this.querySelector('#{cap_name}-kpi-status'),
            kpiVersion: this.querySelector('#{cap_name}-kpi-version'),
            kpiContracts: this.querySelector('#{cap_name}-kpi-contracts'),
            tabsBar: this.querySelector('#{tabs_id}'),
            panelsHost: this.querySelector('#{panels_id}'),
            overviewBody: this.querySelector('#{cap_name}-overview-body'),
            btnRefresh: this.querySelector('#{cap_name}-btn-refresh')
        }};
    }}

    bindEvents() {{
        if (this.dom.btnRefresh) {{
            this.dom.btnRefresh.addEventListener('click', () => {{
                this.fetchHealth();
                this.loadContracts();
            }});
        }}
        if (this.dom.tabsBar) {{
            this.dom.tabsBar.querySelectorAll('.openmfe-tab-btn').forEach(btn => {{
                btn.addEventListener('click', () => this.switchTab(btn.getAttribute('data-tab') || 'overview'));
            }});
        }}
    }}

    switchTab(tabId) {{
        this.activeTab = tabId;
        if (!this.dom.tabsBar || !this.dom.panelsHost) return;
        this.dom.tabsBar.querySelectorAll('.openmfe-tab-btn').forEach(btn => {{
            btn.classList.toggle('is-active', btn.getAttribute('data-tab') === tabId);
        }});
        this.dom.panelsHost.querySelectorAll('.openmfe-panel').forEach(panel => {{
            panel.classList.toggle('is-active', panel.id === `panel-${{tabId}}`);
        }});
    }}

    onMount() {{
        this.fetchHealth();
        this.loadContracts();
        this.registerPoll(() => this.fetchHealth(), 5000);
    }}

    async fetchHealth() {{
        try {{
            const data = await this.apiFetch('/api/v1/health');
            if (this.dom.kpiStatus) this.dom.kpiStatus.textContent = (data && data.status) || 'Healthy';
            if (this.dom.kpiVersion && data && data.version) this.dom.kpiVersion.textContent = `v${{data.version}}`;
            if (this.dom.overviewBody) {{
                this.dom.overviewBody.innerHTML = `<pre class="openmfe-code-preview">${{JSON.stringify(data, null, 2)}}</pre>`;
            }}
        }} catch (err) {{
            if (this.dom.kpiStatus) this.dom.kpiStatus.textContent = 'Offline';
            if (this.showError && this.dom.overviewBody) {{
                this.showError(this.dom.overviewBody, `Health check failed: ${{err.message}}`, () => this.fetchHealth());
            }}
        }}
    }}

    async loadContracts() {{
        const helper = window.BastienMFEContracts;
        if (!helper || !this.dom.tabsBar || !this.dom.panelsHost) return;
        const envelope = await helper.fetchContracts({{
            primaryUrls: [this.apiUrl('/api/v1/contracts')],
            serviceName: '{cap_name}'
        }});
        if (this.dom.kpiContracts) {{
            const count = Array.isArray(envelope.contracts) ? envelope.contracts.length : 0;
            this.dom.kpiContracts.textContent = envelope.reliable ? `${{count}} contract(s)` : 'Unavailable';
        }}
        helper.mountContractTabs({{
            rootEl: this,
            tabsBarEl: this.dom.tabsBar,
            panelsHostEl: this.dom.panelsHost,
            envelope,
            activeTab: this.activeTab,
            onSwitchTab: (tab) => this.switchTab(tab),
            onRetry: () => this.loadContracts()
        }});
    }}
}}

if (window.BastienMFEElement && typeof window.BastienMFEElement.register === 'function') {{
    window.BastienMFEElement.register('{tag_name}', {class_name});
}} else if (typeof customElements !== 'undefined' && !customElements.get('{tag_name}')) {{
    customElements.define('{tag_name}', {class_name});
}}
"""

# -----------------------------------------------------------------------------

def generate_go_scaffold(target_dir: Path, name: str, port: int, desc: str, dry_run: bool) -> None:
    """Generates the Go microservice skeleton and source files."""
    cap_name = name.replace("-", "_")

    # 1. cmd/<name>/main.go
    main_go = f"""package main

// =============================================================================
// [STARTER TEMPLATE / EXAMPLE ENTRYPOINT]
// NOTE: This is a scaffolded Go service entrypoint generated by scaffold_microservice.py.
// Developers & AI Agents: Extend or replace this file with your actual service logic.
//
// ESSENTIAL PROCESS:
// Boots and initializes the {name} microservice, establishing
// dynamic capabilities discovery and lifecycle management.
//
// DATA FLOW:
// 1. Input: Loads configuration using the layered microservice-toolbox loader.
// 2. Logic: Starts core service controllers and listens on canonical capability ports.
// 3. Output: Runs service workers under graceful lifecycle supervision.
//
// KEY PARAMETERS:
// - {cap_name}: Capabilities section defining service network ports and parameters.
// =============================================================================

import (
	"context"
	"fmt"
	"net/http"
	"os"

	"github.com/Bastien-Antigravity/{name}/src/core"
	"github.com/Bastien-Antigravity/{name}/src/rest"
	toolbox_bootstrap "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/bootstrap"
	toolbox_lifecycle "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/lifecycle"
	toolbox_spec "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/spec"
)

// -----------------------------------------------------------------------------

func main() {{
	// 1. Initialize Service via Unified Ecosystem Bootstrapper
	appConfig, appLogger := toolbox_bootstrap.BootstrapService("{name}")
	defer appLogger.Close()

	appLogger.Info("Starting {name} (version %s) under profile: %s", appConfig.GetVersion(), appConfig.Profile)

	// 2. Resolve Service Listen Address (Zero Silent Fallback)
	addr, err := appConfig.GetListenAddr("{cap_name}")
	if err != nil || addr == "" {{
		appLogger.Critical("Failed to resolve dynamic listen address for capability '{cap_name}': %v", err)
		os.Exit(1)
	}}

	// 3. Instantiate Core Controller & REST/OpenMFE Handler
	ctrl := core.NewController(appConfig, appLogger)
	restHandler := rest.NewHandler(appConfig, appLogger, addr)
	mux := http.NewServeMux()
	restHandler.RegisterRoutes(mux)
	httpSrv := &http.Server{{Addr: addr, Handler: rest.CorsMiddleware(mux)}}

	// Dynamic Hot-Reload Listener (Ecosystem Live Configuration Standard)
	appConfig.OnLiveConfUpdate(func(update map[string]interface{{}}) {{
		appLogger.Info("Live configuration update received from config-server: hot-reloading parameters")
		ctrl.OnLiveConfigUpdate(update)
	}})

	// 4. Initialize Lifecycle Manager
	lm := toolbox_lifecycle.NewManagerWithLogger(appLogger)

	lm.Register("StopHTTP", func() error {{
		return httpSrv.Shutdown(context.Background())
	}})
	lm.Register("StopService", func() error {{
		appLogger.Info("Stopping {name} worker...")
		return ctrl.Stop(context.Background())
	}})

	// 5. Register OpenMFE Specification + Exchange Contracts (Non-blocking background loop)
	_ = toolbox_spec.PublishWithLifecycle(appConfig, appLogger, lm, "{cap_name}", toolbox_spec.ServiceSpec{{
		Name:        "{name}",
		Tag:         "{name}-mfe",
		URL:         fmt.Sprintf("http://%s/static/js/mfe-loader.js", addr),
		NavTitle:    "{name}",
		Layer:       "L2",
		Category:    "Domain Services",
		Priority:    100,
		Icon:        "fa-cubes",
		Description: "{desc}",
		Protocol:    "HTTP/1.1 REST",
		Framing:     fmt.Sprintf("Port %d REST", toolbox_spec.ResolveContractPort(addr)),
		DocLink:     "obsidian-brain/06-Microservices/{name}.md",
		Contracts:   rest.BuildServiceContracts(addr),
	}})

	// 6. Start Service Worker Loop & HTTP/OpenMFE Server
	go func() {{
		if err := ctrl.Start(addr); err != nil {{
			appLogger.Critical("Service worker failed: %v", err)
			os.Exit(1)
		}}
	}}()
	go func() {{
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {{
			appLogger.Error("HTTP OpenMFE server error: %v", err)
		}}
	}}()

	// 7. Await OS Signals for Graceful Termination
	lm.Wait(context.Background())
}}
"""
    create_file(target_dir / f"cmd/{name}/main.go", main_go, dry_run)

    # 2. src/core/controller.go
    controller_go = f"""package core

// =============================================================================
// [STARTER TEMPLATE / DUMMY WORKER CONTROLLER]
// NOTE: This is a dummy example controller demonstrating clean lifecycle management.
// Developers & AI Agents: Replace this starter implementation with your domain logic.
//
// ESSENTIAL PROCESS:
// Central business logic controller for {name}.
//
// DATA FLOW:
// 1. Input: Requests, events, and configuration states.
// 2. Logic: Executes domain transformations and coordinates components.
// 3. Output: Telemetry, event publishes, and structured logs.
//
// KEY PARAMETERS:
// - None
// =============================================================================

import (
	"context"

	toolbox_config "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	unilog_interfaces "github.com/Bastien-Antigravity/universal-logger/src/interfaces"
)

// -----------------------------------------------------------------------------

// Controller manages the lifecycle and operations of {name}.
type Controller struct {{
	appConfig *toolbox_config.AppConfig
	logger    unilog_interfaces.Logger
}}

// -----------------------------------------------------------------------------

// NewController instantiates a new {name} Controller.
func NewController(appConfig *toolbox_config.AppConfig, logger unilog_interfaces.Logger) *Controller {{
	return &Controller{{
		appConfig: appConfig,
		logger:    logger,
	}}
}}

// -----------------------------------------------------------------------------

// Version returns the dynamically resolved version of the service from microservice-toolbox.
func (c *Controller) Version() string {{
	if c.appConfig != nil {{
		return c.appConfig.GetVersion()
	}}
	return "0.0.1"
}}

// -----------------------------------------------------------------------------

// Start initializes internal workers and listens on the given address.
func (c *Controller) Start(addr string) error {{
	c.logger.Info("{name} (version %s) controller running on %s", c.Version(), addr)
	return nil
}}

// -----------------------------------------------------------------------------

// Stop terminates active workers gracefully.
func (c *Controller) Stop(ctx context.Context) error {{
	c.logger.Info("{name} controller shutdown complete")
	return nil
}}

// -----------------------------------------------------------------------------

// OnLiveConfigUpdate handles real-time configuration changes without restarting the process.
func (c *Controller) OnLiveConfigUpdate(update map[string]interface{{}}) {{
	c.logger.Info("{name} controller: applying dynamic configuration update without restart")
}}
"""
    create_file(target_dir / "src/core/controller.go", controller_go, dry_run)

    # 3. src/interfaces/interfaces.go
    interfaces_go = f"""package interfaces

// =============================================================================
// [STARTER TEMPLATE / DUMMY INTERFACE CONTRACT]
// NOTE: This is an example interface contract demonstrating decoupling.
// Developers & AI Agents: Replace with your service interfaces.
//
// ESSENTIAL PROCESS:
// Defines domain interfaces for {name} to maintain strict decoupling.
//
// DATA FLOW:
// Contract definitions consumed by concrete providers.
// =============================================================================

import "context"

// -----------------------------------------------------------------------------

// Service defines the contract for {name} operations.
type Service interface {{
	Execute(ctx context.Context) error
}}
"""
    create_file(target_dir / "src/interfaces/interfaces.go", interfaces_go, dry_run)

    # 4. src/models/models.go
    models_go = f"""package models

// =============================================================================
// [STARTER TEMPLATE / DUMMY MODEL SCHEMA]
// NOTE: This is an example data model schema.
// Developers & AI Agents: Replace or extend this with your domain models.
//
// ESSENTIAL PROCESS:
// Data structures and schemas for {name}.
// =============================================================================

// StatusPayload represents the operational health telemetry of {name}.
type StatusPayload struct {{
	ServiceName string `json:"service_name"`
	Status      string `json:"status"`
	Timestamp   int64  `json:"timestamp"`
}}
"""
    create_file(target_dir / "src/models/models.go", models_go, dry_run)

    # 5. go.mod
    go_mod = f"""module github.com/Bastien-Antigravity/{name}

go 1.25

require (
	github.com/Bastien-Antigravity/distributed-config v0.0.0
	github.com/Bastien-Antigravity/flexible-logger v0.0.0
	github.com/Bastien-Antigravity/microservice-toolbox v0.0.0
	github.com/Bastien-Antigravity/safe-socket v0.0.0
	github.com/Bastien-Antigravity/universal-logger v0.0.0
)

replace (
	github.com/Bastien-Antigravity/distributed-config => ../distributed-config
	github.com/Bastien-Antigravity/flexible-logger => ../flexible-logger
	github.com/Bastien-Antigravity/microservice-toolbox => ../microservice-toolbox
	github.com/Bastien-Antigravity/safe-socket => ../safe-socket
	github.com/Bastien-Antigravity/universal-logger => ../universal-logger
)
"""
    create_file(target_dir / "go.mod", go_mod, dry_run)

    # 6. .golangci.yml
    golangci_yml = """version: "2"
run:
  timeout: 5m

linters:
  enable:
    - staticcheck
    - govet
    - ineffassign
  exclusions:
    rules:
      - linters:
          - staticcheck
        text: "QF1008"
"""
    create_file(target_dir / ".golangci.yml", golangci_yml, dry_run)

    # 7. src/core/controller_test.go
    controller_test_go = f"""package core

import (
	"context"
	"testing"

	toolbox_config "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	unilog_interfaces "github.com/Bastien-Antigravity/universal-logger/src/interfaces"
)

// mockLogger embeds unilog_interfaces.Logger to ensure decoupling and interface compatibility.
type mockLogger struct {{
	unilog_interfaces.Logger
}}

func (m *mockLogger) Info(format string, args ...interface{{}})     {{}}
func (m *mockLogger) Warning(format string, args ...interface{{}})  {{}}
func (m *mockLogger) Error(format string, args ...interface{{}})    {{}}
func (m *mockLogger) Critical(format string, args ...interface{{}}) {{}}
func (m *mockLogger) Debug(format string, args ...interface{{}})    {{}}
func (m *mockLogger) Close()                                      {{}}

func TestController_Lifecycle(t *testing.T) {{
	cfg := &toolbox_config.AppConfig{{Profile: "test"}}
	logger := &mockLogger{{}}

	ctrl := NewController(cfg, logger)
	if ctrl == nil {{
		t.Fatal("expected NewController to return non-nil instance")
	}}

	if err := ctrl.Start("127.0.0.1:{port}"); err != nil {{
		t.Fatalf("unexpected Start error: %v", err)
	}}

	if err := ctrl.Stop(context.Background()); err != nil {{
		t.Fatalf("unexpected Stop error: %v", err)
	}}
}}
"""
    create_file(target_dir / "src/core/controller_test.go", controller_test_go, dry_run)

    # 8. src/rest/contracts.go
    contracts_go = f"""package rest

// =============================================================================
// ESSENTIAL PROCESS:
// Builds authoritative Exchange Contracts for {name} published via
// GET /api/v1/contracts and ServiceSpec OpenMFE registration.
//
// DATA FLOW:
// 1. Input: Resolved runtime listen address and configuration metadata.
// 2. Logic: Constructs typed toolbox_spec.ExchangeContract descriptors.
// 3. Output: Returns Exchanges & ContractsEnvelope for OpenMFE Live Operations.
//
// KEY PARAMETERS:
// - listenAddr: Dynamic HTTP listen address resolved from AppConfig.
// =============================================================================

import (
	toolbox_spec "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/spec"
)

// -----------------------------------------------------------------------------

// BuildServiceContracts returns the authoritative ExchangeContract list for {name}.
func BuildServiceContracts(listenAddr string) []toolbox_spec.ExchangeContract {{
	addr := toolbox_spec.DisplayAddress(listenAddr)
	p := toolbox_spec.ResolveContractPort(listenAddr)
	if p == 0 {{
		p = {port}
	}}
	return []toolbox_spec.ExchangeContract{{
		{{
			ID:        "http-rest",
			Type:      "HTTP/1.1 JSON REST",
			TabLabel:  "REST API",
			Icon:      "fa-globe",
			Direction: "inbound",
			Transport: "HTTP/1.1 + CORS JSON",
			Address:   addr,
			Port:      p,
			Framing:   "JSON request/response endpoints",
			Auth:      "Internal mesh CORS",
			Summary:   "{desc}",
			Source:    "{name}/src/rest/rest_handler.go",
			Peers: []toolbox_spec.ContractPeer{{
				{{Service: "web_interface", Role: "consumer", Description: "Renders OpenMFE shell & Exchange Contract tabs"}},
			}},
			Operations: []toolbox_spec.ContractOperation{{
				{{Name: "Health", Kind: "GET", Target: "/api/v1/health", Output: "status/version JSON", Description: "Service health probe"}},
				{{Name: "Contracts", Kind: "GET", Target: "/api/v1/contracts", Output: "ContractsEnvelope JSON", Description: "Self-describing exchange contracts"}},
				{{Name: "MFEBundle", Kind: "GET", Target: "/static/js/mfe-loader.js", Output: "ES6 Web Component JS", Description: "Embedded OpenMFE bundle"}},
			}},
			SchemaFormat: "http",
			Schema:       "GET /api/v1/health\\nGET /api/v1/contracts\\nGET /static/js/mfe-loader.js",
		}},
	}}
}}

// -----------------------------------------------------------------------------

// BuildContractsEnvelope wraps BuildServiceContracts in a versioned ContractsEnvelope.
func BuildContractsEnvelope(listenAddr, version string) toolbox_spec.ContractsEnvelope {{
	return toolbox_spec.NewContractsEnvelope(
		"{cap_name}",
		version,
		"{name}/src/rest/contracts.go",
		BuildServiceContracts(listenAddr),
	)
}}
"""
    create_file(target_dir / "src/rest/contracts.go", contracts_go, dry_run)

    # 9. src/rest/mfe.js
    create_file(target_dir / "src/rest/mfe.js", generate_openmfe_component_js(name, cap_name, desc), dry_run)

    # 10. src/rest/rest_handler.go
    rest_handler_go = f"""package rest

// =============================================================================
// ESSENTIAL PROCESS:
// Serves embedded OpenMFE Web Component assets, CORS middleware, health probe,
// and authoritative GET /api/v1/contracts endpoint for {name}.
//
// DATA FLOW:
// 1. Input: Incoming HTTP requests from web-interface or peer diagnostics.
// 2. Logic: Applies CORS headers and routes to JSON / embedded JS handlers.
// 3. Output: HTTP JSON envelopes or embedded mfe.js Web Component script.
//
// KEY PARAMETERS:
// - addr: Runtime listen address for self-describing Exchange Contracts.
// =============================================================================

import (
	_ "embed"
	"encoding/json"
	"net/http"

	toolbox_config "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/config"
	unilog_interfaces "github.com/Bastien-Antigravity/universal-logger/src/interfaces"
)

//go:embed mfe.js
var mfeJS string

// -----------------------------------------------------------------------------

// Handler exposes HTTP/REST and OpenMFE endpoints for {name}.
type Handler struct {{
	appConfig *toolbox_config.AppConfig
	logger    unilog_interfaces.Logger
	addr      string
}}

// -----------------------------------------------------------------------------

// NewHandler creates a REST Handler for {name}.
func NewHandler(appConfig *toolbox_config.AppConfig, logger unilog_interfaces.Logger, addr string) *Handler {{
	return &Handler{{appConfig: appConfig, logger: logger, addr: addr}}
}}

// -----------------------------------------------------------------------------

// CorsMiddleware attaches CORS headers for cross-origin OpenMFE mounting.
func CorsMiddleware(next http.Handler) http.Handler {{
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {{
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == http.MethodOptions {{
			w.WriteHeader(http.StatusOK)
			return
		}}
		next.ServeHTTP(w, r)
	}})
}}

// -----------------------------------------------------------------------------

// RegisterRoutes mounts REST and OpenMFE handlers on mux.
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {{
	mfeHandler := func(w http.ResponseWriter, r *http.Request) {{
		w.Header().Set("Content-Type", "application/javascript")
		_, _ = w.Write([]byte(mfeJS))
	}}
	mux.HandleFunc("/static/js/mfe-loader.js", mfeHandler)
	mux.HandleFunc("/static/mfe.js", mfeHandler)
	mux.HandleFunc("/api/v1/health", h.handleHealth)
	mux.HandleFunc("/api/v1/contracts", h.handleContracts)
}}

// -----------------------------------------------------------------------------

func (h *Handler) version() string {{
	if h.appConfig != nil {{
		return h.appConfig.GetVersion()
	}}
	return "0.0.1"
}}

func (h *Handler) handleHealth(w http.ResponseWriter, r *http.Request) {{
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{{}}{{
		"service": "{cap_name}",
		"status":  "Healthy",
		"version": h.version(),
	}})
}}

func (h *Handler) handleContracts(w http.ResponseWriter, r *http.Request) {{
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(BuildContractsEnvelope(h.addr, h.version()))
}}
"""
    create_file(target_dir / "src/rest/rest_handler.go", rest_handler_go, dry_run)

    # 11. src/rest/rest_handler_test.go
    rest_test_go = f"""package rest

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	toolbox_spec "github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/spec"
)

func TestHandlerContractsAndMFE(t *testing.T) {{
	h := NewHandler(nil, nil, "127.0.0.1:{port}")
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/contracts", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {{
		t.Fatalf("expected 200 OK, got %d", rec.Code)
	}}
	var env toolbox_spec.ContractsEnvelope
	if err := json.Unmarshal(rec.Body.Bytes(), &env); err != nil {{
		t.Fatalf("failed to decode envelope: %v", err)
	}}
	if !env.Reliable || !env.Exhaustive || len(env.Contracts) == 0 {{
		t.Fatalf("unexpected envelope: %+v", env)
	}}

	mfeReq := httptest.NewRequest(http.MethodGet, "/static/js/mfe-loader.js", nil)
	mfeRec := httptest.NewRecorder()
	mux.ServeHTTP(mfeRec, mfeReq)
	if mfeRec.Code != http.StatusOK || !strings.Contains(mfeRec.Body.String(), "BastienMFEContracts") {{
		t.Fatalf("expected MFE script with BastienMFEContracts, got status=%d", mfeRec.Code)
	}}
}}
"""
    create_file(target_dir / "src/rest/rest_handler_test.go", rest_test_go, dry_run)

# -----------------------------------------------------------------------------

def generate_rust_scaffold(target_dir: Path, name: str, port: int, desc: str, dry_run: bool) -> None:
    """Generates the Rust microservice skeleton and source files."""
    cap_name = name.replace("-", "_")

    # 0. build.rs (Dynamic Versioning Standard from VERSION.txt)
    build_rs = f"""// =============================================================================
// ESSENTIAL PROCESS:
// Dynamic version resolution build script for {name}.
// Reads VERSION.txt from repository root as single source of truth.
// =============================================================================

fn main() {{
    let version = std::fs::read_to_string("VERSION.txt")
        .or_else(|_| std::fs::read_to_string("../VERSION.txt"))
        .unwrap_or_else(|_| env!("CARGO_PKG_VERSION").to_string());
    println!("cargo:rustc-env=APP_VERSION={{}}", version.trim());
    println!("cargo:rerun-if-changed=VERSION.txt");
    println!("cargo:rerun-if-changed=../VERSION.txt");
}}
"""
    create_file(target_dir / "build.rs", build_rs, dry_run)

    # 1. Cargo.toml
    cargo_toml = f"""[package]
name = "{name}"
version = "0.0.1"
edition = "2021"
build = "build.rs"
description = "{desc}"

[dependencies]
tokio = {{ version = "1.38", features = ["full"] }}
serde = {{ version = "1.0", features = ["derive"] }}
serde_json = "1.0"
microservice-toolbox = {{ git = "https://github.com/Bastien-Antigravity/microservice-toolbox.git", branch = "develop" }}

[dev-dependencies]
tokio-test = "0.4"
"""
    create_file(target_dir / "Cargo.toml", cargo_toml, dry_run)

    # 2. src/main.rs
    main_rs = f"""// =============================================================================
// [STARTER TEMPLATE / EXAMPLE ENTRYPOINT]
// NOTE: This is a scaffolded Rust service entrypoint generated by scaffold_microservice.py.
// Developers & AI Agents: Extend or replace this file with your actual service logic.
//
// ESSENTIAL PROCESS:
// Boots and initializes the {name} microservice with Tokio runtime.
//
// DATA FLOW:
// 1. Input: Loads configuration from standalone profile.
// 2. Logic: Starts core service controller.
// 3. Output: Runs service workers under graceful Tokio lifecycle supervision.
//
// KEY PARAMETERS:
// - {cap_name}: Capability section defining service network ports.
// =============================================================================

mod contracts;
mod core;

use microservice_toolbox::spec::{{publish_with_lifecycle, ServiceSpec}};

pub const VERSION: &str = env!("APP_VERSION");

// -----------------------------------------------------------------------------

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {{
    let listen_addr = "127.0.0.1:{port}";
    println!("Starting {name} (version {{}})...", VERSION);

    // 1. Initialize Controller & Exchange Contracts
    let ctrl = core::Controller::new("{name}");
    ctrl.start(listen_addr).await?;
    let _contracts = contracts::build_exchange_contracts(listen_addr);

    // 2. Register OpenMFE ServiceSpec (attach contracts when app_config is loaded)
    let _spec_template = ServiceSpec {{
        name: "{name}".to_string(),
        tag: "{name}-mfe".to_string(),
        url: format!("http://{{}}/static/mfe.js", listen_addr),
        nav_title: "{name}".to_string(),
        layer: "L2".to_string(),
        category: "Domain Services".to_string(),
        priority: 100,
        icon: "fa-cubes".to_string(),
        capability: "{cap_name}".to_string(),
        description: "{desc}".to_string(),
        protocol: "SafeSocket TCP / gRPC".to_string(),
        framing: format!("Port {port}"),
        doc_link: "obsidian-brain/06-Microservices/{name}.md".to_string(),
        contracts: _contracts,
        ..Default::default()
    }};
    let _ = publish_with_lifecycle;

    // Await termination signal
    tokio::signal::ctrl_c().await?;
    println!("Termination signal received, shutting down {name}...");

    ctrl.stop().await?;
    Ok(())
}}
"""
    create_file(target_dir / "src/main.rs", main_rs, dry_run)

    # 2b. src/contracts.rs
    contracts_rs = f"""// =============================================================================
// ESSENTIAL PROCESS:
// Builds authoritative Exchange Contracts for {name} using microservice_toolbox::spec.
//
// DATA FLOW:
// Returns Vec<ExchangeContract> published via ServiceSpec and contract queries.
//
// KEY PARAMETERS:
// - listen_addr: Resolved runtime address for the microservice.
// =============================================================================

use microservice_toolbox::spec::{{ContractOperation, ContractPeer, ExchangeContract}};

// -----------------------------------------------------------------------------

pub fn build_exchange_contracts(listen_addr: &str) -> Vec<ExchangeContract> {{
    vec![ExchangeContract {{
        id: "primary-transport".to_string(),
        r#type: "SafeSocket TCP / gRPC".to_string(),
        tab_label: "Primary Transport".to_string(),
        icon: "fa-exchange".to_string(),
        direction: "inbound".to_string(),
        transport: "Framed TCP / gRPC".to_string(),
        address: listen_addr.to_string(),
        port: {port},
        framing: "4-byte length prefix".to_string(),
        auth: "Internal service mesh".to_string(),
        summary: "{desc}".to_string(),
        source: "{name}/src/contracts.rs".to_string(),
        peers: vec![ContractPeer {{
            service: "web_interface".to_string(),
            role: "consumer".to_string(),
            description: "Renders OpenMFE Exchange Contract tabs".to_string(),
        }}],
        operations: vec![ContractOperation {{
            name: "Health".to_string(),
            kind: "RPC".to_string(),
            target: "{cap_name}/Health".to_string(),
            input: "Empty".to_string(),
            output: "Status".to_string(),
            description: "Service health probe".to_string(),
        }}],
        schema_format: "wire".to_string(),
        schema: format!("{name} listening on {{}}", listen_addr),
    }}]
}}
"""
    create_file(target_dir / "src/contracts.rs", contracts_rs, dry_run)

    # 3. src/core/mod.rs
    core_rs = f"""// =============================================================================
// [STARTER TEMPLATE / DUMMY WORKER CONTROLLER]
// NOTE: This is an example controller demonstrating clean async worker management.
//
// ESSENTIAL PROCESS:
// Central business logic controller for {name}.
//
// DATA FLOW:
// Coordinates background tasks and handles health checks.
//
// KEY PARAMETERS:
// - None
// =============================================================================

pub struct Controller {{
    pub name: String,
}}

// -----------------------------------------------------------------------------

impl Controller {{
    pub fn new(name: &str) -> Self {{
        Self {{
            name: name.to_string(),
        }}
    }}

    pub async fn start(&self, addr: &str) -> Result<(), Box<dyn std::error::Error>> {{
        println!("{{}} controller running on {{}}", self.name, addr);
        Ok(())
    }}

    pub async fn stop(&self) -> Result<(), Box<dyn std::error::Error>> {{
        println!("{{}} controller shutdown complete", self.name);
        Ok(())
    }}

    pub fn on_live_config_update(&self) {{
        println!("{{}} controller: applying dynamic configuration update without restart", self.name);
    }}
}}
"""
    create_file(target_dir / "src/core/mod.rs", core_rs, dry_run)

    # 4. tests/test_basic.rs
    test_rs = f"""// =============================================================================
// [STARTER TEMPLATE / DUMMY TEST SUITE]
// NOTE: Starter integration test for {name}.
// =============================================================================

#[path = "../src/contracts.rs"]
mod contracts;

#[tokio::test]
async fn test_scaffold_initialization() {{
    let built = contracts::build_exchange_contracts("127.0.0.1:{port}");
    assert!(!built.is_empty(), "expected at least one ExchangeContract");
    assert_eq!(built[0].id, "primary-transport");
}}
"""
    create_file(target_dir / "tests/test_basic.rs", test_rs, dry_run)

# -----------------------------------------------------------------------------

def generate_python_scaffold(target_dir: Path, name: str, port: int, desc: str, dry_run: bool) -> None:
    """Generates the Python microservice skeleton and architecture folders."""
    cap_name = name.replace("-", "_")

    # 1. main.py
    main_py = f"""#!/usr/bin/env python
# coding:utf-8

\"\"\"
================================================================================
[STARTER TEMPLATE / EXAMPLE ENTRYPOINT]
NOTE: This is a scaffolded entrypoint example generated by scaffold_microservice.py.
Developers & AI Agents: Replace or extend this file with your actual business logic,
event subscribers, background workers, or API endpoints.
================================================================================

ESSENTIAL PROCESS:
Entry point for the {name} microservice.

DATA FLOW:
1. Input: Loads configuration via microservice-toolbox.
2. Logic: Boots controller and connects to ecosystem capabilities.
3. Output: Telemetry, event publishing, and logs.

KEY PARAMETERS:
- {cap_name}: Primary capability configuration.
\"\"\"

import sys
from pathlib import Path

# Bootstrap configuration and logger via microservice-toolbox
from microservice_toolbox.config.loader import load_config
from microservice_toolbox.logger import UniLog
from microservice_toolbox import publish_with_lifecycle, ServiceSpec
from microservice_toolbox.wiretap import configure_from_config
from src.core.controller import Controller
from src.rest.contracts import build_service_contracts

def main():
    # Load layered configuration (CLI > local YAML > native.yaml > ENV)
    config = load_config("standalone")
    logger = UniLog(app_name="{name}", config_profile="standalone")
    configure_from_config("{name}", config)

    # Resolve capability listen address (Fallback gracefully for local sandbox runs)
    try:
        listen_addr = config.get_listen_addr("{cap_name}") or ""
    except Exception:
        listen_addr = ""

    # Instantiate and start the example worker controller
    controller = Controller(config=config, logger=logger)

    # Dynamic Hot-Reload Listener (Ecosystem Live Configuration Standard)
    if hasattr(config, "on_live_conf_update"):
        config.on_live_conf_update(lambda update: controller.on_live_config_update(update))

    contract_env = build_service_contracts(config=config)

    # Register OpenMFE Specification + Exchange Contracts (non-blocking background thread)
    publish_with_lifecycle(
        config,
        logger,
        lm=None,
        capability="{cap_name}",
        spec=ServiceSpec(
            name="{name}",
            tag="{name}-mfe",
            url=f"http://{{listen_addr or '127.0.0.1'}}/static/mfe.js",
            nav_title="{name}",
            layer="L2",
            category="Domain Services",
            priority=100,
            icon="fa-cubes",
            description="{desc}",
            protocol="HTTP/1.1 REST",
            framing=f"Port {port} REST",
            doc_link="obsidian-brain/06-Microservices/{name}.md",
            contracts=contract_env.get("contracts", []),
        ),
    )

    logger.info(f"Starting {name} (version {{config.get_version()}}) under profile: {{config.profile}}...")
    controller.start()

if __name__ == "__main__":
    main()
"""
    create_file(target_dir / "main.py", main_py, dry_run)

    # 2. src/core/controller.py
    controller_py = f"""#!/usr/bin/env python
# coding:utf-8

\"\"\"
================================================================================
[STARTER TEMPLATE / DUMMY WORKER CONTROLLER]
NOTE: This is a dummy example controller demonstrating the Bastien-Antigravity
Python Integration Specialist coding standards:
  1. One-Class Rule: Exactly one primary class per file.
  2. Keyword-Only Arguments (*): Enforces explicit named arguments for safety.
  3. Standard Constructor: Injects 'config' and 'logger', defaults Name.
Developers & AI Agents: Replace this dummy worker controller with your domain-specific
business processing, background loops, or message handlers.
================================================================================

ESSENTIAL PROCESS:
Central domain controller managing workers and lifecycle for {name}.

DATA FLOW:
1. Input: Configuration and logger injected via constructor.
2. Logic: Coordinates background tasks and handles health checks.
3. Output: Telemetry events and operational logs.

KEY PARAMETERS:
- config: Ecosystem configuration provider.
- logger: Unified logger instance.
\"\"\"

from typing import Any, Optional

class Controller:
    \"\"\"
    Example dummy controller managing lifecycle and operations of {name}.
    Replace this with your actual microservice controller implementation.
    \"\"\"

    def __init__(self, *, config: Any, logger: Any, name: Optional[str] = None):
        self.config = config
        self.logger = logger
        self.Name = name or self.__class__.__name__
        self.version = self._load_version()

    def _load_version(self) -> str:
        \"\"\"Loads version dynamically from microservice-toolbox / VERSION.txt.\"\"\"
        if hasattr(self.config, "get_version"):
            return self.config.get_version()
        try:
            from microservice_toolbox.version import get_version
            return get_version(caller_file=__file__)
        except Exception:
            return "0.0.1"

    def start(self) -> None:
        # Example starter logic - replace with actual background workers
        self.logger.info(f"{{self.Name}} (version {{self.version}}) : [DUMMY] Controller started successfully.")

    def stop(self) -> None:
        # Example cleanup logic - replace with actual worker teardown
        self.logger.info(f"{{self.Name}} : [DUMMY] Controller terminated gracefully.")

    def on_live_config_update(self, update: dict) -> None:
        \"\"\"Handles real-time configuration changes without restarting the process.\"\"\"
        self.logger.info(f"{{self.Name}} : applying dynamic configuration update without restart.")
"""
    create_file(target_dir / "src/core/controller.py", controller_py, dry_run)

    # 3. src/interfaces/service.py
    service_py = f"""#!/usr/bin/env python
# coding:utf-8

\"\"\"
================================================================================
[STARTER TEMPLATE / DUMMY PROTOCOL CONTRACT]
NOTE: This is a dummy example interface protocol demonstrating type decoupling.
Developers & AI Agents: Define your service-specific protocols, contracts, and
abstract base classes here to keep domain logic decoupled from external I/O.
================================================================================

ESSENTIAL PROCESS:
Contract definitions and protocols for {name}.

DATA FLOW:
Protocol definitions consumed by concrete provider implementations.

KEY PARAMETERS:
- ServiceProtocol: Example base operational protocol.
\"\"\"

from typing import Protocol, runtime_checkable

@runtime_checkable
class ServiceProtocol(Protocol):
    \"\"\"Example protocol contract. Replace with domain operations.\"\"\"
    def execute(self) -> bool:
        ...
"""
    create_file(target_dir / "src/interfaces/service.py", service_py, dry_run)

    # 4. src/models/status.py
    status_py = f"""#!/usr/bin/env python
# coding:utf-8

\"\"\"
================================================================================
[STARTER TEMPLATE / DUMMY DATA MODEL]
NOTE: This is a dummy example data model demonstrating:
  1. Dataclass usage for typed payload structures.
  2. Language-idiomatic naming standard for domain models (e.g. StatusPayload).
Developers & AI Agents: Replace or extend this file with your actual service schemas,
telemetry models, and request/response payloads.
================================================================================

ESSENTIAL PROCESS:
Data models and schemas for {name}.

DATA FLOW:
Structured payload models for status reporting and health telemetry.

KEY PARAMETERS:
- StatusPayload: Example health telemetry dataclass.
\"\"\"

from dataclasses import dataclass
import time

@dataclass
class StatusPayload:
    \"\"\"Example dummy status payload model.\"\"\"
    service_name: str
    status: str
    timestamp: float = time.time()
"""
    create_file(target_dir / "src/models/status.py", status_py, dry_run)

    # 5. requirements.txt
    reqs_txt = """microservice-toolbox
universal-logger
fastapi
uvicorn
pytest
"""
    create_file(target_dir / "requirements.txt", reqs_txt, dry_run)

    # 6. src/rest/contracts.py, mfe.js, rest_handler.py
    contracts_py = f"""#!/usr/bin/env python
# coding:utf-8

\"\"\"
ESSENTIAL PROCESS:
Builds authoritative Exchange Contracts for {name} via microservice_toolbox.contracts.

DATA FLOW:
1. Input: Optional FastAPI app and AppConfig instance.
2. Logic: Introspects live FastAPI routes into ContractOperation descriptors.
3. Output: Returns ContractsEnvelope dict for GET /api/v1/contracts & ServiceSpec.

KEY PARAMETERS:
- app: Optional FastAPI instance whose routes are introspected live.
- config: Optional AppConfig providing runtime addresses and semver.
\"\"\"

from typing import Any, Dict

from microservice_toolbox.contracts import (
    ContractOperation,
    ContractPeer,
    ExchangeContract,
    build_contracts_envelope,
    display_address,
    extract_fastapi_operations,
    resolve_contract_port,
)

# -----------------------------------------------------------------------------

def build_service_contracts(app: Any = None, config: Any = None, version: str = "") -> Dict[str, Any]:
    \"\"\"Builds the authoritative Exchange Contracts envelope for {name}.\"\"\"
    addr = ""
    if config is not None and hasattr(config, "get_listen_addr"):
        try:
            addr = config.get_listen_addr("{cap_name}") or ""
        except Exception:
            addr = ""
    ver = version or (config.get_version() if hasattr(config, "get_version") else "0.0.1")

    rest_ops = extract_fastapi_operations(app)
    if not rest_ops:
        rest_ops = [
            ContractOperation(name="health", kind="GET", target="/api/v1/health", output="status/version JSON", description="Service health check"),
            ContractOperation(name="contracts", kind="GET", target="/api/v1/contracts", output="ContractsEnvelope JSON", description="Authoritative exchange contracts"),
            ContractOperation(name="mfe_bundle", kind="GET", target="/static/mfe.js", output="ES6 Web Component JS", description="Embedded OpenMFE bundle"),
        ]

    contracts = [
        ExchangeContract(
            id="http-rest",
            type="HTTP/1.1 JSON REST",
            tab_label="REST API",
            icon="fa-globe",
            direction="inbound",
            transport="HTTP/1.1 + FastAPI JSON",
            address=display_address(addr),
            port=resolve_contract_port(addr) or {port},
            framing="JSON request/response endpoints",
            auth="Internal mesh CORS",
            summary="{desc}",
            source="{name}/src/rest/rest_handler.py",
            peers=[
                ContractPeer(service="web_interface", role="consumer", description="Hosts OpenMFE shell & Exchange Contract tabs"),
            ],
            operations=rest_ops,
            schema_format="http",
            schema="\\n".join(f"{{op.kind:<6}} {{op.target}}" for op in rest_ops),
        )
    ]

    return build_contracts_envelope(
        "{cap_name}",
        ver,
        "{name}/src/rest/contracts.py",
        contracts,
    )
"""
    create_file(target_dir / "src/rest/contracts.py", contracts_py, dry_run)
    create_file(target_dir / "src/rest/mfe.js", generate_openmfe_component_js(name, cap_name, desc), dry_run)

    rest_handler_py = f"""#!/usr/bin/env python
# coding:utf-8

\"\"\"
ESSENTIAL PROCESS:
Registers FastAPI HTTP/REST, /api/v1/contracts, and OpenMFE static JS routes for {name}.

DATA FLOW:
1. Input: FastAPI app instance.
2. Logic: Binds CORS middleware and health/contracts/mfe.js handlers.
3. Output: Live REST and OpenMFE HTTP routes.

KEY PARAMETERS:
- app: FastAPI application instance.
\"\"\"

from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from src.rest.contracts import build_service_contracts

# -----------------------------------------------------------------------------

_MFE_JS_PATH = Path(__file__).resolve().with_name("mfe.js")

def register_routes(app, config=None) -> None:
    \"\"\"Registers OpenMFE static asset, health, and Exchange Contract routes on FastAPI.\"\"\"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    async def health():
        ver = config.get_version() if hasattr(config, "get_version") else "0.0.1"
        return {{"service": "{cap_name}", "status": "Healthy", "version": ver}}

    @app.get("/api/v1/contracts")
    async def get_contracts():
        return JSONResponse(content=build_service_contracts(app=app, config=config))

    def _serve_mfe():
        content = _MFE_JS_PATH.read_text(encoding="utf-8") if _MFE_JS_PATH.is_file() else ""
        return Response(content=content, media_type="application/javascript")

    app.add_api_route("/static/mfe.js", _serve_mfe, methods=["GET"])
    app.add_api_route("/static/js/mfe-loader.js", _serve_mfe, methods=["GET"])
"""
    create_file(target_dir / "src/rest/rest_handler.py", rest_handler_py, dry_run)

    # 7. tests/test_basic.py
    test_py = f"""#!/usr/bin/env python
# coding:utf-8

# =============================================================================
# [STARTER TEMPLATE / TEST SUITE]
# Verifies starter initialization and Exchange Contracts payload generation for {name}.
# =============================================================================

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.rest.contracts import build_service_contracts


def test_scaffold_initialization():
    \"\"\"Verify Exchange Contracts envelope builds cleanly for {name}.\"\"\"
    envelope = build_service_contracts()
    assert envelope["service"] == "{cap_name}"
    assert envelope["reliable"] is True
    assert envelope["exhaustive"] is True
    assert len(envelope["contracts"]) >= 1
"""
    create_file(target_dir / "tests/test_basic.py", test_py, dry_run)

# -----------------------------------------------------------------------------

def generate_cpp_scaffold(target_dir: Path, name: str, port: int, desc: str, dry_run: bool) -> None:
    """Generates a C++17 microservice skeleton wired to microservice-toolbox/cpp spec & contracts."""
    cap_name = name.replace("-", "_")

    # 1. src/contracts/contracts.hpp
    contracts_hpp = f"""#ifndef {cap_name.upper()}_CONTRACTS_HPP
#define {cap_name.upper()}_CONTRACTS_HPP

/*
 * ESSENTIAL PROCESS:
 * Builds authoritative C++ Exchange Contracts for {name} using
 * microservice_toolbox::spec::ExchangeContract and ContractsEnvelope.
 *
 * DATA FLOW:
 * 1. Input: Dynamic listen address and runtime semver.
 * 2. Logic: Normalizes endpoints and constructs typed contract descriptors.
 * 3. Output: Serializes ContractsEnvelope JSON and feeds ServiceSpec registration.
 *
 * KEY PARAMETERS:
 * - listenAddr: Resolved host:port address from AppConfig::GetListenAddr().
 */

#include <string>
#include <vector>

#include "microservice_toolbox/spec/contracts.hpp"

namespace {cap_name} {{
namespace contracts {{

// -----------------------------------------------------------------------------

inline std::vector<microservice_toolbox::spec::ExchangeContract> BuildServiceContracts(const std::string& listenAddr) {{
    using namespace microservice_toolbox::spec;
    ExchangeContract primary;
    primary.id = "tcp-wire";
    primary.type = "Framed TCP / C++ Wire";
    primary.tabLabel = "Wire Protocol";
    primary.icon = "fa-exchange";
    primary.direction = "inbound";
    primary.transport = "SafeSocket TCP / Custom Binary";
    primary.address = DisplayAddress(listenAddr);
    int resolvedPort = ResolveContractPort(listenAddr);
    primary.port = resolvedPort > 0 ? resolvedPort : {port};
    primary.framing = "4-byte length prefix";
    primary.auth = "Internal service mesh";
    primary.summary = "{desc}";
    primary.source = "{name}/src/contracts/contracts.hpp";
    primary.peers = {{
        ContractPeer{{"web_interface", "consumer", "Displays Exchange Contract tabs"}}
    }};
    primary.operations = {{
        ContractOperation{{"Health", "FRAME", "{cap_name}/health", "Ping", "Pong", "Low-latency liveness probe"}},
        ContractOperation{{"Status", "GET", "/api/v1/contracts", "", "ContractsEnvelope JSON", "Authoritative exchange contracts"}}
    }};
    primary.schemaFormat = "wire";
    primary.schema = "{name} listening on " + primary.address;
    return {{primary}};
}}

// -----------------------------------------------------------------------------

inline microservice_toolbox::spec::ContractsEnvelope BuildContractsEnvelope(
    const std::string& listenAddr,
    const std::string& version) {{
    return microservice_toolbox::spec::NewContractsEnvelope(
        "{cap_name}",
        version,
        "{name}/src/contracts/contracts.hpp",
        BuildServiceContracts(listen_addr_fallback(listenAddr)));
}}

}} // namespace contracts
}} // namespace {cap_name}

#endif
"""
    # Clean typo 'listen_addr_fallback(listenAddr)' -> just 'listenAddr' cleanly:
    contracts_hpp = contracts_hpp.replace("listen_addr_fallback(listenAddr)", "listenAddr")
    create_file(target_dir / "src/contracts/contracts.hpp", contracts_hpp, dry_run)

    # 2. src/core/controller.hpp
    controller_hpp = f"""#ifndef {cap_name.upper()}_CONTROLLER_HPP
#define {cap_name.upper()}_CONTROLLER_HPP

/*
 * ESSENTIAL PROCESS:
 * Central C++ domain controller managing lifecycle and live config updates for {name}.
 *
 * DATA FLOW:
 * 1. Input: AppConfig pointer and shared Logger instance.
 * 2. Logic: Resolves dynamic semver and applies live hot-reload configuration updates.
 * 3. Output: Controlled start/stop execution and structured telemetry logs.
 *
 * KEY PARAMETERS:
 * - appConfig: Resolved microservice_toolbox::config::AppConfig instance.
 */

#include <memory>
#include <string>

#include "microservice_toolbox/config/AppConfig.hpp"
#include "microservice_toolbox/utils/Logger.hpp"
#include "microservice_toolbox/version/Version.hpp"

namespace {cap_name} {{
namespace core {{

// -----------------------------------------------------------------------------

class Controller {{
public:
    Controller(std::shared_ptr<microservice_toolbox::config::AppConfig> cfg,
               std::shared_ptr<microservice_toolbox::utils::Logger> logger)
        : config_(std::move(cfg)), logger_(std::move(logger)) {{}}

    std::string GetVersion() const {{
        if (config_) {{
            return config_->GetVersion();
        }}
        return microservice_toolbox::version::GetVersion();
    }}

    void Start(const std::string& addr) {{
        if (logger_) {{
            logger_->Info("{name} (version " + GetVersion() + ") controller running on " + addr);
        }}
    }}

    void Stop() {{
        if (logger_) {{
            logger_->Info("{name} controller shutdown complete");
        }}
    }}

    void OnLiveConfigUpdate(const std::string&) {{
        if (logger_) {{
            logger_->Info("{name} controller: applying dynamic configuration update without restart");
        }}
    }}

private:
    std::shared_ptr<microservice_toolbox::config::AppConfig> config_;
    std::shared_ptr<microservice_toolbox::utils::Logger> logger_;
}};

}} // namespace core
}} // namespace {cap_name}

#endif
"""
    create_file(target_dir / "src/core/controller.hpp", controller_hpp, dry_run)

    # 3. src/main.cpp
    main_cpp = f"""/*
 * ESSENTIAL PROCESS:
 * Entry point for the C++17 {name} microservice. Loads AppConfig, initializes
 * LifecycleManager, registers ServiceSpec + Exchange Contracts with web-interface,
 * and starts the domain controller.
 *
 * DATA FLOW:
 * 1. Input: Standalone/fleet configuration via microservice-toolbox AppConfig.
 * 2. Logic: Publishes ServiceSpec and ExchangeContracts on background lifecycle thread.
 * 3. Output: Runs core controller until SIGINT/SIGTERM signal shutdown.
 *
 * KEY PARAMETERS:
 * - {cap_name}: Capability block defining listen address and endpoints.
 */

#include <iostream>
#include <memory>
#include <string>

#include "microservice_toolbox/config/AppConfig.hpp"
#include "microservice_toolbox/lifecycle/LifecycleManager.hpp"
#include "microservice_toolbox/spec/spec.hpp"
#include "contracts/contracts.hpp"
#include "core/controller.hpp"

// -----------------------------------------------------------------------------

int main(int argc, char** argv) {{
    std::shared_ptr<microservice_toolbox::config::AppConfig> appConfig =
        microservice_toolbox::config::LoadConfig("standalone", argc, argv);
    auto appLogger = appConfig ? appConfig->GetLogger() : nullptr;

    std::string addr = appConfig->GetListenAddr("{cap_name}");
    if (addr.empty()) {{
        if (appLogger) {{
            appLogger->Critical("Failed to resolve dynamic listen address for '{cap_name}'");
        }}
        return 1;
    }}

    {cap_name}::core::Controller ctrl(appConfig, appLogger);
    microservice_toolbox::lifecycle::LifecycleManager lm;
    lm.Register("StopService", [&ctrl]() {{ ctrl.Stop(); }});

    microservice_toolbox::spec::ServiceSpec spec;
    spec.name = "{name}";
    spec.tag = "{name}-mfe";
    spec.url = "http://" + addr;
    spec.navTitle = "{name}";
    spec.layer = "L2";
    spec.category = "Domain Services";
    spec.priority = 100;
    spec.icon = "fa-cubes";
    spec.description = "{desc}";
    spec.protocol = "TCP Wire";
    spec.framing = "Port {port}";
    spec.docLink = "obsidian-brain/06-Microservices/{name}.md";
    spec.contracts = {cap_name}::contracts::BuildServiceContracts(addr);

    microservice_toolbox::spec::SpecPublisher::PublishWithLifecycle(
        *appConfig, appLogger, &lm, "{cap_name}", spec);

    ctrl.Start(addr);
    lm.Wait();
    return 0;
}}
"""
    create_file(target_dir / "src/main.cpp", main_cpp, dry_run)

    # 4. tests/test_basic.cpp
    test_cpp = f"""/*
 * ESSENTIAL PROCESS:
 * Unit tests verifying C++ Exchange Contract generation and ServiceSpec serialization for {name}.
 */

#include <cassert>
#include <iostream>

#include "microservice_toolbox/spec/spec.hpp"
#include "../src/contracts/contracts.hpp"

int main() {{
    auto env = {cap_name}::contracts::BuildContractsEnvelope("127.0.0.1:{port}", "0.0.1");
    auto j = env.ToJson();
    assert(j["service"] == "{cap_name}");
    assert(j["reliable"] == true);
    assert(j["exhaustive"] == true);
    assert(j["contracts"].size() == 1);

    microservice_toolbox::spec::ServiceSpec spec;
    spec.name = "{name}";
    spec.tag = "{name}-mfe";
    spec.contracts = {cap_name}::contracts::BuildServiceContracts("127.0.0.1:{port}");
    auto specJson = spec.ToJson();
    assert(specJson["contracts"].size() == 1);

    std::cout << "C++ scaffold tests passed for {name}." << std::endl;
    return 0;
}}
"""
    create_file(target_dir / "tests/test_basic.cpp", test_cpp, dry_run)

# -----------------------------------------------------------------------------

def generate_common_files(target_dir: Path, name: str, lang: str, port: int, desc: str, dry_run: bool) -> None:
    """Generates files mandatory across all languages: Dockerfile, compose, AGENTS.md, etc."""
    cap_name = name.replace("-", "_")

    # 1. Dockerfile (Multi-stage compliant with 12-Docker-Deployment-Standards.md)
    if lang == "go":
        dockerfile = f"""# === BUILD STAGE ===
FROM golang:1.25-alpine AS builder

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"

RUN apk add --no-cache git gcc musl-dev ca-certificates tzdata

WORKDIR /workspace

# Clone shared library modules for replace directives in builder stage
RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git /workspace/microservice-toolbox && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/distributed-config.git /workspace/distributed-config && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/safe-socket.git /workspace/safe-socket && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/universal-logger.git /workspace/universal-logger && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/flexible-logger.git /workspace/flexible-logger

# Copy service source
WORKDIR /workspace/{name}
COPY . .

# Ensure dependencies are tidy and build binary
RUN go mod tidy && \\
    CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /{name}-bin ./cmd/{name}

# === RUNTIME STAGE ===
FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /{name}

COPY --from=builder /{name}-bin /{name}/{name}

ENTRYPOINT ["/{name}/{name}"]
"""
    elif lang == "rust":
        dockerfile = f"""# === BUILD STAGE ===
FROM rust:1.80-alpine AS builder

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"

RUN apk add --no-cache musl-dev gcc git

WORKDIR /workspace/{name}
COPY . .

RUN cargo build --release

# === RUNTIME STAGE ===
FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /{name}

COPY --from=builder /workspace/{name}/target/release/{name} /{name}/{name}

ENTRYPOINT ["/{name}/{name}"]
"""
    elif lang == "cpp":
        dockerfile = f"""# === BUILD STAGE (Compile CGO shared libraries + C++ binary) ===
FROM golang:1.25-alpine AS go-builder

WORKDIR /workspace
RUN apk add --no-cache git gcc musl-dev libc-dev
RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git /workspace/microservice-toolbox && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/distributed-config.git /workspace/distributed-config && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/universal-logger.git /workspace/universal-logger && \\
    cd /workspace/distributed-config && go build -buildmode=c-shared -o /workspace/libdistconf.so ./cmd/libdistconf && \\
    cd /workspace/universal-logger && go build -buildmode=c-shared -o /workspace/libunilog.so ./src/cgo_bridge

FROM alpine:3.20 AS cpp-builder
RUN apk add --no-cache g++ make
WORKDIR /workspace
COPY --from=go-builder /workspace/microservice-toolbox /workspace/microservice-toolbox
COPY --from=go-builder /workspace/libdistconf.so /usr/local/lib/libdistconf.so
COPY --from=go-builder /workspace/distributed-config/distconf/libdistconf /workspace/distributed-config/distconf/libdistconf
WORKDIR /workspace/{name}
COPY . .
RUN g++ -std=c++17 -O2 -Wall -Wextra -Isrc -I/workspace/microservice-toolbox/cpp/include -I/workspace/distributed-config/distconf/libdistconf src/main.cpp -o /{name}-bin -L/usr/local/lib -ldistconf

# === RUNTIME STAGE ===
FROM alpine:3.20
LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"
RUN apk add --no-cache ca-certificates tzdata libstdc++
WORKDIR /{name}
COPY --from=go-builder /workspace/libdistconf.so /usr/local/lib/libdistconf.so
COPY --from=go-builder /workspace/libunilog.so /usr/local/lib/libunilog.so
COPY --from=cpp-builder /{name}-bin /{name}/{name}
ENTRYPOINT ["/{name}/{name}"]
"""
    else:
        dockerfile = f"""# === BUILD STAGE (Compile CGO libunilog.so) ===
FROM golang:1.25-alpine AS go-builder

WORKDIR /workspace

RUN apk add --no-cache git gcc musl-dev libc-dev

RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git /workspace/microservice-toolbox && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/distributed-config.git /workspace/distributed-config && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/safe-socket.git /workspace/safe-socket && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/universal-logger.git /workspace/universal-logger && \\
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/flexible-logger.git /workspace/flexible-logger && \\
    cd /workspace/universal-logger && \\
    go build -buildmode=c-shared -o /workspace/libunilog.so ./src/cgo_bridge

# === PYTHON RUNTIME STAGE ===
FROM python:3.12-alpine

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{name}"

RUN apk add --no-cache ca-certificates tzdata git build-base

WORKDIR /{name}

# Install compiled libunilog.so system-wide
COPY --from=go-builder /workspace/libunilog.so /usr/local/lib/libunilog.so

# Clone & install microservice-toolbox python package
RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git /tmp/microservice-toolbox && \\
    pip install --no-cache-dir /tmp/microservice-toolbox/python && \\
    rm -rf /tmp/microservice-toolbox

# Install service dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY . .

ENTRYPOINT ["python3", "main.py"]
"""
    create_file(target_dir / "Dockerfile", dockerfile, dry_run)

    # 2. docker-compose.yml (Local fragment)
    compose_yml = f"""services:
  {name}:
    build:
      context: .
      dockerfile: Dockerfile
    image: ghcr.io/bastien-antigravity/{name}:${{TAG:-latest}}
    container_name: {name}
    restart: unless-stopped
    ports:
      - "${{HOST_IP:-127.0.0.1}}:{port}:{port}"
    volumes:
      - ./standalone.yaml:/{name}/standalone.yaml:ro
    networks:
      - teleremote-network

networks:
  teleremote-network:
    name: teleremote-network
    external: true
"""
    create_file(target_dir / "docker-compose.yml", compose_yml, dry_run)

    # 3. AGENTS.md
    if lang == "go":
        test_cmd = "go test -v ./..."
        build_cmd = f"go build -o bin/{name} ./cmd/{name}"
        run_cmd = f"./bin/{name}"
    elif lang == "python":
        test_cmd = "pytest"
        build_cmd = "pip install -r requirements.txt"
        run_cmd = "python3 main.py"
    elif lang == "cpp":
        test_cmd = "make test"
        build_cmd = "make build"
        run_cmd = f"./bin/{name}"
    else:
        test_cmd = "cargo test"
        build_cmd = "cargo build"
        run_cmd = f"./target/debug/{name}"

    agents_md = f"""# AGENTS.md: {name}

## Service Mission & Architecture Role
`{name}` is responsible for: {desc}.

- **Exposed Capability**: `{cap_name}` (Port: `{port}`)
- **Shared Libraries**: `microservice-toolbox`, `universal-logger`, `distributed-config`, `safe-socket`
- **Configuration Link**: `standalone.yaml -> ../docker-deployment/modes/local/config/native.yaml`

## Key Build & Test Commands
```bash
# Build binary
{build_cmd}

# Run tests
{test_cmd}

# Run service locally
{run_cmd}
```

## AI Development & Integration Guidelines
1. **Bootstrap Ritual**: Initialized using `toolbox_bootstrap.BootstrapService("{name}")` (Go), `load_config` / `bootstrap_microservice` (Python/Rust), or `LoadConfig` (C++). Never bypass the toolbox bootstrapper.
2. **Dynamic Port Resolution**: Always use `appConfig.GetListenAddr("{cap_name}")` or `GetCapability("{cap_name}", &cap)`. NEVER hardcode IP or port numbers.
3. **Encrypted Secrets**: Sensitive values stored in configurations must remain encrypted as `ENC(...)` tokens until runtime decryption via `appConfig.DecryptSecret()`.
4. **Header Ritual**: All source files MUST begin with the standard Triple-Block header (`ESSENTIAL PROCESS`, `DATA FLOW`, `KEY PARAMETERS`).
5. **Section Dividers**: Use appropriate dividers (`// -----------------------------------------------------------------------------`) between exported methods and major sections.
6. **Dynamic Fleet Hot-Reloading**: Microservices must register `OnLiveConfUpdate` / `on_live_conf_update` to dynamically reload configuration changes without restarting the daemon process.
7. **Service Specification, OpenMFE & Authoritative Exchange Contracts Standard**:
   - Register declarative `ServiceSpec` + `Contracts` (`ExchangeContract[]`) during bootstrap using `spec.PublishWithLifecycle` (Go), `spec.publish_with_lifecycle` (Python), `spec::publish_with_lifecycle` (Rust), or `SpecPublisher::PublishWithLifecycle` (C++, with `contracts.hpp` / `contracts.h` for C ABI) with infinite resilience (`MaxRetries: -1`) and non-blocking execution.
   - HTTP services MUST expose `GET /api/v1/contracts` (`ContractsEnvelope`) built from live runtime routes and embedded schemas, and OpenMFE components (`mfe.js`) MUST use `BastienMFEElement` + `window.BastienMFEContracts` inside `.openmfe-tabs-bar` (`div[3]`) without fabricating mock schemas or using brittle `?v=` CSS query strings.
8. **Real-Time Transport WireTap & Dynamic Topology (`> L3` Ready)**: `BootstrapService` (Go) and `init_microservice` / `configure_from_config` (Python) automatically bind the lock-free WireTap transport telemetry engine (`microservice-toolbox/go/pkg/wiretap`, `microservice_toolbox/wiretap.py`) to `safe-socket`, gRPC (`teleremote`, `notification`, `network`), and NATS (`messaging`). Combined with `spec.PublishWithLifecycle`, this microservice (`L2`, `L3`, or `> L3` / `L4+`) and its live edges and segregated channels are synthesized automatically on `web-interface` (`src/router/mesh_topology.go`) with zero hardcoded topology changes in `web-interface`.
"""
    create_file(target_dir / "AGENTS.md", agents_md, dry_run)

    # 4. AI-Init.md
    init_md = f"""---
microservice: {name}
type: governance
status: active
---

# ⚡ AI Initialization: {name}

> [!IMPORTANT] MANDATORY INITIALIZATION
> Copy and paste this prompt when starting a new session in this repository:
> 
> "1. Read the ecosystem map in **[[Ecosystem-Map-MOC]]**."
> "2. Load project constraints from **[[AI-Project-DNA]]**."
> "3. Restore session state from **[[AI-Session-State]]**."
> "4. **Sentinel Audit**: Run `python3 08-Squad-Agent/main.py preflight-check` and resolve any drift."
> "5. **Squad Protocol**: You are now the **Lead Developer**. Identify and hire the required **Specialists** from `07-Core-KMS/Role-Prompts/03-Developer/Squad/`."
"""
    create_file(target_dir / "AI-Init.md", init_md, dry_run)

    # 5. AI-Project-DNA.md
    dna_md = f"""# Metadata
- Version: 0.0.1
- Classification: Level 1 Microservice

---
microservice: {name}
type: note
status: active
tags:
- '#service/{name}'
- '#type/note'
- '#state/active'
- '#zone/3-fleet'
---

# 🧬 Project DNA: {name}

## 🎯 High-Level Intent (BDD)
- **Goal**: {desc}
- **Behavioral Source of Truth**: [[02-Business-BDD/02-Behavior-Specs/{name}/FEAT-001-Initialization.md]]

## 🛠️ Role Specifics
- **Architect**: Ensure sovereign configuration resolution via microservice-toolbox and adherence to ecosystem networking.
- **QA**: Validate unit test coverage and integration scenarios in sandbox-testing.
- **Developer**: Fulfill the capability contract defined in AGENTS.md.

## 🚦 Lifecycle & Versioning
- **Primary Branch**: `develop`
- **Protected Branches**: `main`, `master`
- **Versioning Strategy**: Semantic Versioning (v0.0.1).
- **Version Source of Truth**: `VERSION.txt`.
"""
    create_file(target_dir / "AI-Project-DNA.md", dna_md, dry_run)

    # 6. AI-Session-State.md
    session_md = f"""---
microservice: {name}
type: session-state
status: active
tags:
  - '#service/{name}'
  - '#type/session-state'
  - '#state/active'
  - '#zone/3-fleet'
---

# AI Session State: {name}

Mission-ID: MISSION-SCAFFOLD-001
Status: Initialized / Ready
"""
    create_file(target_dir / "AI-Session-State.md", session_md, dry_run)

    # 7. TODO.md
    todo_md = f"""# TODO: {name}

- [ ] Implement core business logic controllers
- [ ] Connect inter-service dependencies via microservice-toolbox
- [ ] Implement end-to-end integration tests in sandbox-testing
"""
    create_file(target_dir / "TODO.md", todo_md, dry_run)

    # 8. README.md
    readme_md = f"""# {name}

{desc}

## Architecture & Integration
See [AGENTS.md](AGENTS.md) for technical specifications, capability ports, and AI development rules.
"""
    create_file(target_dir / "README.md", readme_md, dry_run)

    # 6. VERSION.txt
    create_file(target_dir / "VERSION.txt", "0.0.1\n", dry_run)

    # 7. Makefile (Dynamic Versioning Standard - Go, Rust, C++ compiled projects)
    if lang == "go":
        makefile = f"""VERSION ?= $(shell cat VERSION.txt 2>/dev/null || echo "0.0.1")
LDFLAGS := -s -w -X 'github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/version.BuildVersion=$(VERSION)'

.PHONY: all build test race vet version clean run

all: build

version:
\t@echo $(VERSION)

build:
\t@echo "Building {name} (version $(VERSION))..."
\t@mkdir -p bin
\tgo build -ldflags="$(LDFLAGS)" -o bin/{name} ./cmd/{name}

test:
\t@echo "Running tests for {name} (version $(VERSION))..."
\tgo test -v ./...

race:
\t@echo "Running race detector (version $(VERSION))..."
\tgo test -race -v ./...

vet:
\t@echo "Running go vet..."
\tgo vet ./...

run:
\t./bin/{name}

clean:
\t@echo "Cleaning build artifacts..."
\t@rm -rf bin/ dist/ build/
"""
        create_file(target_dir / "Makefile", makefile, dry_run)
    elif lang == "rust":
        makefile = f"""VERSION ?= $(shell cat VERSION.txt 2>/dev/null || echo "0.0.1")

.PHONY: all build test version clean run

all: build

version:
\t@echo $(VERSION)

build:
\t@echo "Building {name} (version $(VERSION))..."
\tcargo build --release

test:
\t@echo "Running tests for {name} (version $(VERSION))..."
\tcargo test

run:
\tcargo run

clean:
\t@echo "Cleaning build artifacts..."
\tcargo clean
"""
        create_file(target_dir / "Makefile", makefile, dry_run)
    elif lang == "cpp":
        makefile = f"""VERSION ?= $(shell cat VERSION.txt 2>/dev/null || echo "0.0.1")
CXX ?= g++
DISTCONF_DIR ?= ../distributed-config/distconf/libdistconf
TOOLBOX_CPP_INC ?= ../microservice-toolbox/cpp/include
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Isrc -I$(TOOLBOX_CPP_INC) -I$(DISTCONF_DIR) -DAPP_VERSION=\\"$(VERSION)\\"
LDFLAGS ?= -L$(DISTCONF_DIR) -ldistconf -Wl,-rpath,$(DISTCONF_DIR)

.PHONY: all build test version clean run

all: build

version:
\t@echo $(VERSION)

build:
\t@echo "Building {name} (version $(VERSION))..."
\t@mkdir -p bin
\t$(CXX) $(CXXFLAGS) src/main.cpp -o bin/{name} $(LDFLAGS)

test:
\t@echo "Running C++ tests for {name} (version $(VERSION))..."
\t@mkdir -p bin
\t$(CXX) $(CXXFLAGS) tests/test_basic.cpp -o bin/test_basic $(LDFLAGS)
\tDYLD_LIBRARY_PATH="$(DISTCONF_DIR):$$DYLD_LIBRARY_PATH" LD_LIBRARY_PATH="$(DISTCONF_DIR):$$LD_LIBRARY_PATH" ./bin/test_basic

run:
\tDYLD_LIBRARY_PATH="$(DISTCONF_DIR):$$DYLD_LIBRARY_PATH" ./bin/{name}

clean:
\t@echo "Cleaning build artifacts..."
\t@rm -rf bin/ build/
"""
        create_file(target_dir / "Makefile", makefile, dry_run)

    # 7. quick-overview/ human onboarding
    qo_dir = target_dir / "quick-overview"
    create_file(qo_dir / "Architecture-Overview.md", f"# Architecture Overview: {name}\n\nHigh-level component overview for human readers.\n", dry_run)
    create_file(qo_dir / "Features-Behavior.md", f"# Features & Behavior: {name}\n\nKey features and behavioral specifications for human readers.\n", dry_run)
    create_file(qo_dir / "Testing-Playbook.md", f"# Testing Playbook: {name}\n\nTesting procedures for human developers.\n", dry_run)
    create_file(qo_dir / "General-Misc.md", f"# General & Miscellaneous: {name}\n\nOperational guidelines and tips.\n", dry_run)
    create_file(qo_dir / ".geminiignore", "*\n", dry_run)
    create_file(qo_dir / ".mcpignore", "*\n", dry_run)
    create_file(qo_dir / ".aiignore", "*\n", dry_run)

    # 8. standalone.yaml symlink
    workspace_root = resolve_workspace_root()
    native_yaml = workspace_root / "docker-deployment" / "modes" / "local" / "config" / "native.yaml"
    if native_yaml.exists():
        rel_link = os.path.relpath(native_yaml, target_dir)
        create_symlink(target_dir / "standalone.yaml", rel_link, dry_run)
    else:
        create_symlink(target_dir / "standalone.yaml", "../docker-deployment/modes/local/config/native.yaml", dry_run)

    # 9. .github CI/CD Workflows and Dependabot (from 05-Fleet-Operation/04-Templates)
    templates_dir = workspace_root / "obsidian-brain" / "05-Fleet-Operation" / "04-Templates"

    ci_template_path = templates_dir / "Microservice" / "ci.yml"
    if ci_template_path.exists():
        ci_content = ci_template_path.read_text(encoding="utf-8")
    else:
        ci_content = """# [FLEET-ARCHITECT] Continuous Integration
name: Fleet CI
on:
  push:
    branches: [ develop ]
  pull_request:
    branches: [ develop ]

jobs:
  fleet-ci:
    uses: Bastien-Antigravity/fleet-operation-brain/.github/workflows/master-ci.yml@develop
    secrets: inherit
"""
    create_file(target_dir / ".github" / "workflows" / "ci.yml", ci_content, dry_run)

    dep_template_path = templates_dir / "Microservice" / "dependabot.yml"
    if dep_template_path.exists():
        dep_content = dep_template_path.read_text(encoding="utf-8")
    else:
        dep_content = """version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "monthly"
"""
    create_file(target_dir / ".github" / "dependabot.yml", dep_content, dry_run)

    # 10. .gitignore
    gitignore_template = templates_dir / "gitignore-global"
    if gitignore_template.exists():
        gi_content = gitignore_template.read_text(encoding="utf-8")
    else:
        gi_content = """# System Files
.DS_Store
*.log
__pycache__/
*.pyc
.venv/
target/
bin/
dist/
"""
    create_file(target_dir / ".gitignore", gi_content, dry_run)

# -----------------------------------------------------------------------------

def generate_bdd_spec(brain_dir: Path, name: str, desc: str, dry_run: bool) -> None:
    """Generates the initial BDD behavior specification note in 02-Business-BDD."""
    bdd_dir = brain_dir / "02-Business-BDD" / "02-Behavior-Specs" / name
    feat_file = bdd_dir / "FEAT-001-Initialization.md"

    content = f"""---
microservice: {name}
type: note
status: active
tags:
- '#service/{name}'
- '#type/note'
- '#state/active'
- '#zone/3-fleet'
---
# FEAT-001: Initialization & Lifecycle Management

*Back-link: [[{name}/README|⬅️ {name}]]*
---

# Feature: Service Bootstrap & Health Supervision

## 🎯 Business Intent
- **User Story**: As a platform operator, I want `{name}` to bootstrap reliably using microservice-toolbox and report health status so that the fleet orchestrator and watchdog-agent can supervise it.
- **Problem Solved**: Eliminates configuration drift, unmonitored crashes, and unhandled SIGINT/SIGTERM terminations.

## 🎬 Scenarios (Gherkin)

### Scenario 1: Clean Startup with Valid Configuration
- **Given** the ecosystem configuration file `standalone.yaml` is present
- **When** `{name}` is launched
- **Then** it must connect to required capabilities without panicking
- **And** it must log an initial startup confirmation via universal-logger
- **And** it must register cleanly with the process lifecycle manager

### Scenario 2: Graceful Termination on OS Signal
- **Given** `{name}` is running
- **When** a SIGINT or SIGTERM signal is received
- **Then** the service must execute all registered shutdown hooks
- **And** it must flush active log buffers
- **And** it must exit with status code 0

## 🛠️ Technical Constraints
- **Bootstrap**: MUST initialize via `microservice-toolbox`.
- **Secrets**: MUST decrypt any `ENC(...)` parameters on demand.
"""
    create_file(feat_file, content, dry_run)

# -----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fabricate a standard Bastien-Antigravity microservice skeleton.")
    parser.add_argument("--name", "-n", help="Microservice name (e.g. market-observer)")
    parser.add_argument("--lang", "-l", choices=["go", "python", "rust", "cpp"], default="go", help="Language (go, python, rust, cpp)")
    parser.add_argument("--port", "-p", type=int, default=8090, help="Default capability listen port")
    parser.add_argument("--desc", "-d", default="Ecosystem microservice component", help="Short mission description")
    parser.add_argument("--dest", help="Destination path (defaults to ../<name>)")
    parser.add_argument("--brain", help="Target knowledge brain directory (defaults to domain brain or obsidian-brain)")
    parser.add_argument("--dry-run", action="store_true", help="Preview file fabrication without writing to disk")

    args = parser.parse_args()

    name = args.name
    if not name:
        name = input("Enter new microservice name (e.g. market-observer): ").strip()
        if not name:
            print("❌ Error: Service name is required.")
            sys.exit(1)

    lang = args.lang
    port = args.port
    desc = args.desc
    dry_run = args.dry_run

    workspace_root = resolve_workspace_root()
    target_dir = Path(args.dest).resolve() if args.dest else workspace_root / name
    if args.brain:
        brain_dir = Path(args.brain).resolve()
    elif (target_dir.parent / "trading-brain").exists():
        brain_dir = target_dir.parent / "trading-brain"
    elif (Path.cwd() / "02-Business-BDD").exists():
        brain_dir = Path.cwd()
    else:
        brain_dir = workspace_root / "obsidian-brain"

    print(f"\n🚀 Fabricating microservice '{name}' ({lang}) at {target_dir}...")

    if target_dir.exists() and not dry_run:
        print(f"⚠️ Warning: Target directory {target_dir} already exists. Proceeding with caution.")

    # 1. Generate language specific scaffold
    if lang == "go":
        generate_go_scaffold(target_dir, name, port, desc, dry_run)
    elif lang == "python":
        generate_python_scaffold(target_dir, name, port, desc, dry_run)
    elif lang == "rust":
        generate_rust_scaffold(target_dir, name, port, desc, dry_run)
    elif lang == "cpp":
        generate_cpp_scaffold(target_dir, name, port, desc, dry_run)

    # 2. Generate common ecosystem files
    generate_common_files(target_dir, name, lang, port, desc, dry_run)

    # 3. Generate BDD specification stub
    generate_bdd_spec(brain_dir, name, desc, dry_run)

    cap_name = name.replace("-", "_")

    print("\n" + "=" * 80)
    print(f"🎉 Microservice '{name}' successfully scaffolded!")
    print("=" * 80)
    print("\n📋 REQUIRED FLEET REGISTRATION CHECKLIST (THE 8 TOUCHPOINTS):")
    print("1. [docker-deployment/modes/local/config/native.yaml] Add capability:")
    print(f"""       {cap_name}:
           ip: ${{HOST_IP:-127.0.0.1}}
           port: "${{{name.upper().replace('-', '_')}_PORT:-{port}}}"
""")
    print(f"2. [docker-deployment/modes/docker/config/services/{name}.yaml] Create container config slice:")
    print(f"""       capabilities:
         {cap_name}:
           ip: 0.0.0.0
           port: "{port}"
         nats_server:
           ip: nats-server
           port: 4222
         log_server:
           ip: log-server
           port: 9020
         config_server:
           ip: config-server
           port: 3306
         timescale_db:
           ip: timescale-db
           port: 5432
""")
    print("3. [docker-deployment/docker-compose.yaml] Add service container:")
    print(f"""     {name}:
       image: ghcr.io/bastien-antigravity/{name}:${{TAG:-develop}}
       build:
         context: ../{name}
         dockerfile: Dockerfile
       container_name: {name}
       restart: unless-stopped
       volumes:
         - ./modes/docker/config/services/{name}.yaml:/{name}/standalone.yaml:ro
       networks:
         teleremote-network:
           aliases:
             - {name}
""")
    print("4. [watchdog-agent/src/config/heal.go] Add symlink target:")
    print(f'       filepath.Join(rootDir, "{name}", "standalone.yaml"),\n')
    print("5. [docker-deployment/scripts/common.py] Add to SERVICES_SPEC (for fleet.sh compile/status):")
    if lang == "go":
        bin_rel = f"{name}/bin/{name}"
        build_c = f'["go", "build", "-o", "bin/{name}" + EXE_EXT, "./cmd/{name}"]'
    elif lang == "rust":
        bin_rel = f"{name}/target/debug/{name}"
        build_c = '["cargo", "build"]'
    elif lang == "cpp":
        bin_rel = f"{name}/bin/{name}"
        build_c = '["make", "build"]'
    else:
        bin_rel = ""
        build_c = "None"
    print(f"""       {{
         "name": "{name}",
         "proc_pattern": "{name}",
         "win_exe": "{name}.exe",
         "rel_dir": "{name}",
         "build_cmd": {build_c},
         "bin_path": "{bin_rel}" + EXE_EXT,
         "port": {port},
         "protocol": "REST",
       }}
""")
    print("6. [obsidian-brain/05-Fleet-Operation/00-Repo-Control/service-registry.json] Register service:")
    print(f"""       {{
         "name": "{name}",
         "image": "ghcr.io/bastien-antigravity/{name}",
         "default_port": {port},
         "protocol": "REST",
         "archetype": "Microservice",
         "classification": "level1_microservice"
       }}
""")
    print("7. [obsidian-brain/05-Fleet-Operation/00-Repo-Control/inventory.json] Register repository:")
    print(f"""       {{
         "name": "{name}",
         "path": "./{name}",
         "remote": "https://github.com/Bastien-Antigravity/{name}.git",
         "master_branch": "develop",
         "repo_type": "level1-microservice"
       }}
       (Or run: python3 obsidian-brain/08-Squad-Agent/main.py build-inventory)
""")
    print("8. [UI & Remote Integration] (Optional / If Interactive):")
    print("   - OpenMFE & Service Spec: Auto-registers with web-interface via spec.PublishWithLifecycle (Go) / spec.publish_with_lifecycle (Python) / spec::publish_with_lifecycle (Rust) / SpecPublisher::PublishWithLifecycle (C++)")
    print("   - Exchange Contracts: Expose GET /api/v1/contracts & populate ServiceSpec.Contracts (Go/Python/Rust/C++) -> rendered via BastienMFEContracts in .openmfe-tabs-bar")
    print("   - Tele-Remote: Push dynamic UI menu over gRPC (Port 1863)")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
