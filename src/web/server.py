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

import sys
import json
import time
import urllib.request
import threading
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# -----------------------------------------------------------------------------

app = FastAPI(title="Squad Control Web Server")

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (MFE script)
_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# -----------------------------------------------------------------------------

def init_routes(controller, logger):
    """Dynamically initializes and registers squad REST routes."""
    from src.rest.rest_handler import SquadRESTHandler
    rest_handler = SquadRESTHandler(controller, logger)
    rest_handler.register_routes(app)

# -----------------------------------------------------------------------------

def register_mfe_with_web_interface(config, logger, sa_ip, sa_port):
    """
    Auto-registration daemon that POSTs our MFE definition to the central web-interface.
    """
    time.sleep(2)  # Wait for server to boot

    # Resolve web_interface address dynamically via standard toolbox accessor (zero silent fallback)
    try:
        web_addr = config.get_listen_addr("web_interface")
    except Exception as e:
        logger.error(f"OpenMFE registration aborted: Failed to resolve capability 'web_interface' listen address ({e}).")
        return

    import os
    brain_id = os.getenv("TARGET_BRAIN_ID") or os.getenv("BRAIN_ID")
    if not brain_id and hasattr(config, "data"):
        try:
            brain_id = config.data.get("capabilities", {}).get("squad_agent", {}).get("target_brain_id")
        except Exception:
            brain_id = None

    is_satellite = brain_id and brain_id not in ("obsidian-brain", "root", "main")
    service_name = f"squad-agent-{brain_id}" if is_satellite else "squad-agent"
    service_tag = "squad-agent-mfe"
    nav_title = f"🚀 Squad: {brain_id.replace('-', ' ').title()}" if is_satellite else "🚀 Squad Control"

    reg_url = f"http://{web_addr}/api/v1/register"
    client_ip = sa_ip if sa_ip not in ("0.0.0.0", "", "::") else "127.0.0.1"
    mfe_url = f"http://{client_ip}:{sa_port}/static/mfe.js"
    
    payload = {
        "name": service_name,
        "tag": service_tag,
        "url": mfe_url,
        "navTitle": nav_title
    }
    
    req_data = json.dumps(payload).encode("utf-8")
    
    logger.info(f"OpenMFE: Starting squad-agent auto-registration loop to {reg_url}")
    backoff = 2.0
    max_backoff = 15.0
    while True:
        try:
            req = urllib.request.Request(
                reg_url, 
                data=req_data, 
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                status = resp.status
                if 200 <= status < 300:
                    logger.info(f"OpenMFE: Successfully registered squad-agent MFE at {reg_url}")
                    return
                else:
                    logger.warning(f"OpenMFE: Registration attempt failed with status {status}; retrying in {backoff:.1f}s...")
        except Exception as e:
            logger.warning(f"OpenMFE: Registration attempt failed ({e}); retrying in {backoff:.1f}s...")
        time.sleep(backoff)
        backoff = min(backoff * 1.5, max_backoff)

# -----------------------------------------------------------------------------

def start_async_server(controller, config, logger, host, port):
    """Launches the uvicorn web server and starts the auto-registration daemon thread."""
    init_routes(controller, logger)
    
    # Spawn registration thread
    t = threading.Thread(
        target=register_mfe_with_web_interface,
        args=(config, logger, host, port),
        daemon=True
    )
    t.start()

    logger.info(f"Starting Squad Control FastAPI server on http://{host}:{port}...")
    
    # Run uvicorn in a non-blocking background task or thread-safe runner
    config_uv = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config_uv)
    
    # We return the server so it can be run or shut down
    return server
