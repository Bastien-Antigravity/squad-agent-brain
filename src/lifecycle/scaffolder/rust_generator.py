#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Generates a compliant Rust 1.91 microservice repository skeleton wired to microservice-toolbox
(load_config, on_live_conf_update, wiretap, publish_with_lifecycle, ExchangeContracts, and
Zone-1 unit tests).

DATA FLOW:
1. Input: Target repository path, service name, default listen port, and mission description.
2. Logic: Emits build.rs, Cargo.toml, src/main.rs, src/contracts.rs, src/core/mod.rs, and
   tests/test_basic.rs, then registers local .cargo/config.toml paths when applicable.
3. Output: Ready-to-compile Rust microservice tree passing strict compliance gates.

KEY PARAMETERS:
- target_dir: Destination repository directory.
- name: Kebab-case microservice identifier.
- port: Primary capability listen port.
"""

from pathlib import Path as pathPath
from typing import Optional as typeOptional

from src.lifecycle.scaffolder.common import (
    _is_core_workspace,
    _register_in_cargo_config,
    _resolve_brain_name,
    create_file,
    resolve_workspace_root,
)

# -----------------------------------------------------------------------------------------------

def generate_rust_scaffold(
    target_dir: pathPath,
    name: str,
    port: int,
    desc: str,
    dry_run: bool,
    layer: str = "L3",
    brain_name: typeOptional[str] = None
) -> None:
    """Generates the Rust microservice skeleton and source files."""
    cap_name = name.replace("-", "_")
    resolved_brain = _resolve_brain_name(target_dir, brain_name)

    # 0. build.rs (Dynamic Versioning Standard from VERSION.txt)
    build_rs = f"""// =============================================================================
// ESSENTIAL PROCESS:
// Dynamic version resolution build script for {name}.
// Reads VERSION.txt from repository root as single source of truth.
// =============================================================================

fn main() {{
    let version = std::fs::read_to_string("VERSION.txt")
        .or_else(|_| std::fs::read_to_string("../VERSION.txt"))
        .expect("CRITICAL: VERSION.txt not found (FAIL-FAST)");
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
    main_rs = f"""//! ESSENTIAL PROCESS:
//! Boots and initializes the {name} microservice with Tokio runtime.
//!
//! DATA FLOW:
//! 1. Input: Loads configuration from standalone profile.
//! 2. Logic: Starts core service controller, WireTap telemetry, and live config reload.
//! 3. Output: Runs service workers under graceful Tokio lifecycle supervision.
//!
//! KEY PARAMETERS:
//! - {cap_name}: Capability section defining service network ports.

mod contracts;
mod core;

use std::sync::Arc;

use microservice_toolbox::config::load_config;
use microservice_toolbox::contracts::display_address;
use microservice_toolbox::spec::{{publish_with_lifecycle, ServiceSpec}};
use microservice_toolbox::wiretap::configure_from_config;

// -----------------------------------------------------------------------------------------------

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {{
    let mut ac = load_config("standalone")?;
    configure_from_config("{name}", &ac);
    let listen_addr = ac.get_listen_addr("{cap_name}")?;
    let version = ac.get_version();
    ac.logger.info(&format!("Starting {name} (version {{}})...", version));

    // 1. Initialize Controller, Live Hot-Reload & Exchange Contracts
    let ctrl = Arc::new(core::Controller::new("{name}", ac.logger.clone()));
    let ctrl_reload = ctrl.clone();
    ac.on_live_conf_update(move |_val| {{
        ctrl_reload.on_live_config_update();
    }});
    ctrl.start(&listen_addr).await?;
    let _contracts = contracts::build_exchange_contracts(&listen_addr);

    // 2. Register OpenMFE ServiceSpec via AppConfig
    let spec_template = ServiceSpec {{
        name: "{name}".to_string(),
        tag: "{name}-mfe".to_string(),
        url: format!("http://{{}}/static/mfe.js", display_address(&listen_addr)),
        nav_title: "{name}".to_string(),
        layer: "{layer}".to_string(),
        category: "Domain Services".to_string(),
        priority: 100,
        icon: "fa-cubes".to_string(),
        capability: "{cap_name}".to_string(),
        description: "{desc}".to_string(),
        protocol: "SafeSocket TCP / gRPC".to_string(),
        framing: format!("Port {{}}", listen_addr.rsplit(':').next().unwrap_or("")),
        doc_link: "{resolved_brain}/06-Microservices/{name}.md".to_string(),
        contracts: _contracts,
        ..Default::default()
    }};
    publish_with_lifecycle(&ac, Some(ac.logger.clone()), None, "{cap_name}", spec_template)?;

    // Await termination signal
    tokio::signal::ctrl_c().await?;
    ac.logger.info("Termination signal received, shutting down {name}...");

    ctrl.stop().await?;
    Ok(())
}}
"""
    create_file(target_dir / "src/main.rs", main_rs, dry_run)

    # 2b. src/contracts.rs
    contracts_rs = f"""//! ESSENTIAL PROCESS:
//! Builds authoritative Exchange Contracts for {name} using microservice_toolbox::spec.
//!
//! DATA FLOW:
//! Returns Vec<ExchangeContract> published via ServiceSpec and contract queries.
//!
//! KEY PARAMETERS:
//! - listen_addr: Resolved runtime address for the microservice.

use microservice_toolbox::contracts::{{display_address, resolve_contract_port}};
use microservice_toolbox::spec::{{ContractOperation, ContractPeer, ExchangeContract}};

// -----------------------------------------------------------------------------------------------

pub fn build_exchange_contracts(listen_addr: &str) -> Vec<ExchangeContract> {{
    vec![ExchangeContract {{
        id: "primary-transport".to_string(),
        r#type: "SafeSocket TCP / gRPC".to_string(),
        tab_label: "Primary Transport".to_string(),
        icon: "fa-exchange".to_string(),
        direction: "inbound".to_string(),
        transport: "Framed TCP / gRPC".to_string(),
        address: display_address(listen_addr),
        port: resolve_contract_port(listen_addr),
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
    core_rs = f"""//! ESSENTIAL PROCESS:
//! Central business logic controller for {name}.
//!
//! DATA FLOW:
//! Coordinates background tasks and handles health checks and dynamic hot-reloads.
//!
//! KEY PARAMETERS:
//! - logger: Shared universal-logger trait object (`Arc<dyn Logger>`) from AppConfig.

use std::sync::Arc;

use microservice_toolbox::logger::Logger;

pub struct Controller {{
    pub name: String,
    logger: Arc<dyn Logger>,
}}

// -----------------------------------------------------------------------------------------------

impl Controller {{
    pub fn new(name: &str, logger: Arc<dyn Logger>) -> Self {{
        Self {{
            name: name.to_string(),
            logger,
        }}
    }}

    pub async fn start(&self, addr: &str) -> Result<(), Box<dyn std::error::Error>> {{
        self.logger.info(&format!("{{}} controller running on {{}}", self.name, addr));
        Ok(())
    }}

    pub async fn stop(&self) -> Result<(), Box<dyn std::error::Error>> {{
        self.logger.info(&format!("{{}} controller shutdown complete", self.name));
        Ok(())
    }}

    pub fn on_live_config_update(&self) {{
        self.logger.info(&format!(
            "{{}} controller: applying dynamic configuration update without restart",
            self.name
        ));
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
    assert_eq!(built[0].port, {port});
}}

#[tokio::test]
async fn test_invalid_address_zero_silent_fallback() {{
    let built = contracts::build_exchange_contracts("");
    assert_eq!(built.len(), 1);
    assert_eq!(built[0].port, 0);
}}
"""
    create_file(target_dir / "tests/test_basic.rs", test_rs, dry_run)

    # Register local Rust library crates in workspace root .cargo/config.toml
    if not dry_run:
        ws_root = resolve_workspace_root()
        if _is_core_workspace(target_dir, ws_root) or (
            (ws_root / ".cargo" / "config.toml").is_file()
            and target_dir.resolve().is_relative_to(ws_root.resolve())
        ):
            _register_in_cargo_config(ws_root, target_dir)
        elif (target_dir.parent / ".cargo" / "config.toml").is_file() or (target_dir.parent / "standalone.yaml").is_file():
            _register_in_cargo_config(target_dir.parent, target_dir)
