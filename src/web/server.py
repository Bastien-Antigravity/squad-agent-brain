#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
FastAPI Web Server for Squad Control Dashboard and MFE registration.
Serves static MFE assets and handles REST API queries.

DATA FLOW:
1. Instantiates FastAPI application and mounts static asset directory.
2. Initializes REST route handlers with command controller and UniLog logger.
3. Automatically registers OpenMFE micro-frontend with central web_interface.
4. Starts uvicorn ASGI server on configured IP and port.

KEY PARAMETERS:
- controller: CommandController singleton instance.
- config: Distributed configuration handle.
- logger: UniLog logging handle.
- host: Network bind host address.
- port: Network bind port number.
"""

from os import environ as osEnviron, getenv as osGetenv
from pathlib import Path as pathPath
from threading import Thread as threadingThread
from fastapi import FastAPI as fastapiFastAPI
from fastapi.staticfiles import StaticFiles as fastapiStaticFiles
from fastapi.middleware.cors import CORSMiddleware as fastapiCORSMiddleware
from uvicorn import Config as uvicornConfig, Server as uvicornServer
from microservice_toolbox.spec import ServiceSpec as toolboxServiceSpec, publish_service_spec as toolboxPublishServiceSpec

# -----------------------------------------------------------------------------------------------

app = fastapiFastAPI(title="Squad Control Web Server")

# Add CORS Middleware
app.add_middleware(
    fastapiCORSMiddleware,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (MFE script)
_STATIC_DIR = pathPath(__file__).parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", fastapiStaticFiles(directory=str(_STATIC_DIR)), name="static")

# -----------------------------------------------------------------------------------------------

def init_routes(controller, logger):
    """Dynamically initializes and registers squad REST routes."""
    from src.rest.rest_handler import SquadRESTHandler
    rest_handler = SquadRESTHandler(controller, logger)
    rest_handler.register_routes(app)

# -----------------------------------------------------------------------------------------------

def register_mfe_with_web_interface(config, logger, sa_ip, sa_port):
    """
    Auto-registration daemon that publishes our ServiceSpec to the central web-interface.
    """
    brain_id = osGetenv("TARGET_BRAIN_ID") or osGetenv("BRAIN_ID")
    if not brain_id:
        brain_id = config.data.get("capabilities", {}).get("squad_agent", {}).get("target_brain_id")

    is_satellite = brain_id and brain_id not in ("obsidian-brain", "root", "main")
    service_name = f"squad-agent-{brain_id}" if is_satellite else "squad-agent"
    service_tag = "squad-agent-mfe"
    nav_title = f"🚀 Squad: {brain_id.replace('-', ' ').title()}" if is_satellite else "🚀 Squad Control"

    if sa_ip in ("0.0.0.0", "", "::"):
        client_ip = osEnviron.get("HOST_IP", "127.0.0.2") if osEnviron.get("DOCKER_ENV") == "true" else "127.0.0.1"
    else:
        client_ip = sa_ip
    mfe_url = f"http://{client_ip}:{sa_port}/static/mfe.js"

    from src.rest.contracts import build_squad_agent_contracts
    contracts_env = build_squad_agent_contracts(app=app, config=config)
    contract_list = contracts_env.get("contracts", [])

    pub_kwargs = dict(
        name=service_name,
        tag=service_tag,
        url=mfe_url,
        nav_title=nav_title,
        layer="L3",
        category="Secure Controls",
        icon="fa-users",
        priority=10,
        requires_auth=True,
        description="Autonomous AI Agent Squad orchestrator managing task execution, code generation, and knowledge indexing.",
        protocol="HTTP/1.1 REST & WebSocket",
        framing=f"Port {sa_port} REST & WS",
        doc_link="obsidian-brain/06-Microservices/Squad-Agent-Hub.md",
        data_structure={"contracts": contract_list},
    )
    if hasattr(toolboxServiceSpec, "__dataclass_fields__") and "contracts" in toolboxServiceSpec.__dataclass_fields__:
        pub_kwargs["contracts"] = contract_list

    toolboxPublishServiceSpec(
        config,
        logger,
        "squad_agent",
        **pub_kwargs,
    )

# -----------------------------------------------------------------------------------------------

def start_async_server(controller, config, logger, host, port):
    """Launches the uvicorn web server and starts the auto-registration daemon thread."""
    init_routes(controller, logger)

    # Spawn registration thread
    t = threadingThread(
        target=register_mfe_with_web_interface,
        args=(config, logger, host, port),
        daemon=True
    )
    t.start()

    logger.info(f"Starting Squad Control FastAPI server on http://{host}:{port}...")

    # Run uvicorn in a non-blocking background task or thread-safe runner
    config_uv = uvicornConfig(app, host=host, port=port, log_level="warning")
    server = uvicornServer(config_uv)

    # We return the server so it can be run or shut down
    return server
