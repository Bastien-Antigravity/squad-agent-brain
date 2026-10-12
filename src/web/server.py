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

    # Resolve web_interface address dynamically from config (no fallbacks)
    web_cap = None
    if config and hasattr(config, "data") and isinstance(config.data, dict):
        web_cap = config.data.get("capabilities", {}).get("web_interface")

    if not web_cap or not isinstance(web_cap, dict):
        logger.error("OpenMFE registration aborted: Missing capability 'capabilities.web_interface' in configuration.")
        return
    if "port" not in web_cap:
        logger.error("OpenMFE registration aborted: Missing 'capabilities.web_interface.port' in configuration.")
        return
    if "ip" not in web_cap:
        logger.error("OpenMFE registration aborted: Missing 'capabilities.web_interface.ip' in configuration.")
        return

    web_ip = str(web_cap["ip"])
    web_port = int(web_cap["port"])

    reg_url = f"http://{web_ip}:{web_port}/api/v1/register"
    mfe_url = f"http://{sa_ip}:{sa_port}/static/mfe.js"
    
    payload = {
        "name": "squad-agent",
        "tag": "squad-agent-mfe",
        "url": mfe_url,
        "navTitle": "🚀 Squad Control"
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
