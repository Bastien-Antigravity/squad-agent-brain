#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Generates a compliant C++17 microservice repository skeleton wired to microservice-toolbox
(LoadConfig, OnLiveConfUpdate, wiretap::ConfigureFromConfig, SpecPublisher, ExchangeContracts,
and standalone Zone-1 CTest unit tests).

DATA FLOW:
1. Input: Target repository path, service name, default listen port, and mission description.
2. Logic: Emits src/main.cpp, src/core/controller.hpp, src/contracts/contracts.hpp, and
   tests/test_basic.cpp using PascalCase public parity methods and 77-dash dividers.
3. Output: Ready-to-build C++17 microservice tree passing strict compliance gates.

KEY PARAMETERS:
- target_dir: Destination repository directory.
- name: Kebab-case microservice identifier.
- port: Primary capability listen port.
"""

from pathlib import Path as pathPath
from typing import Optional as typeOptional

from src.lifecycle.scaffolder.common import (
    _resolve_brain_name,
    _to_pascal_case,
    create_file,
    resolve_workspace_root,
)

# -----------------------------------------------------------------------------------------------

def generate_cpp_scaffold(
    target_dir: pathPath,
    name: str,
    port: int,
    desc: str,
    dry_run: bool,
    layer: str = "L3",
    brain_name: typeOptional[str] = None
) -> None:
    """Generates a C++17 microservice skeleton wired to microservice-toolbox/cpp spec & contracts."""
    cap_name = name.replace("-", "_")
    resolved_brain = _resolve_brain_name(target_dir, brain_name)

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
    primary.port = ResolveContractPort(listenAddr);
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
#include "microservice_toolbox/wiretap/WireTap.hpp"
#include "contracts/contracts.hpp"
#include "core/controller.hpp"

// -----------------------------------------------------------------------------

int main(int argc, char** argv) {{
    std::shared_ptr<microservice_toolbox::config::AppConfig> appConfig =
        microservice_toolbox::config::LoadConfig("standalone", argc, argv);
    auto appLogger = appConfig ? appConfig->GetLogger() : nullptr;
    microservice_toolbox::wiretap::ConfigureFromConfig("{name}", *appConfig);

    std::string addr = appConfig->GetListenAddr("{cap_name}");
    if (addr.empty()) {{
        if (appLogger) {{
            appLogger->Critical("Failed to resolve dynamic listen address for '{cap_name}'");
        }}
        return 1;
    }}

    {cap_name}::core::Controller ctrl(appConfig, appLogger);
    appConfig->OnLiveConfUpdate([&ctrl](const std::string& payload) {{
        ctrl.OnLiveConfigUpdate(payload);
    }});
    microservice_toolbox::lifecycle::LifecycleManager lm;
    lm.Register("StopService", [&ctrl]() {{ ctrl.Stop(); }});

    microservice_toolbox::spec::ServiceSpec spec;
    spec.name = "{name}";
    spec.tag = "{name}-mfe";
    spec.navTitle = "{name}";
    spec.layer = "{layer}";
    spec.category = "Domain Services";
    spec.priority = 100;
    spec.icon = "fa-cubes";
    spec.description = "{desc}";
    spec.protocol = "TCP Wire";
    spec.framing = "Port %s";
    spec.docLink = "{resolved_brain}/06-Microservices/{name}.md";
    spec.contracts = {cap_name}::contracts::BuildServiceContracts(addr);

    // SpecPublisher auto-enriches URL, Framing %s ports, Version (appConfig->GetVersion()), Node, and Health
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
