#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides the REST API endpoints wrapping the Squad Command Controller.
Allows external clients (like web-interface) to query status, switch modes, list commands, and run commands via SSE stream.

DATA FLOW:
1. Client sends HTTP GET/POST or SSE request to /api/v1/ routes.
2. Route handler validates query parameters and payload schema.
3. Controller evaluates command or publishes message onto event bus.
4. Handler returns JSON response or streams Server-Sent Events (SSE).

KEY PARAMETERS:
- controller: CommandController singleton instance.
- logger: UniLog or compatible logging handle.
"""

import os
import json
import time
import asyncio
import sys
from fastapi import FastAPI, APIRouter, Query, HTTPException, Request
from fastapi.responses import StreamingResponse

# -----------------------------------------------------------------------------

class SquadRESTHandler:
    """REST API Handler exposing squad controller capabilities."""

    # -----------------------------------------------------------------------------

    def __init__(self, controller, logger):
        self.controller = controller
        self.logger = logger

    # -----------------------------------------------------------------------------

    def is_github_configured(self) -> bool:
        """Verifies if a valid GitHub personal access token is configured in environment or capability config."""
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if not token and hasattr(self.controller, "config") and self.controller.config:
            try:
                cap_token = getattr(self.controller.config, "data", {}).get("capabilities", {}).get("squad_agent", {}).get("github", {}).get("token", "")
                if isinstance(cap_token, str) and not cap_token.startswith("${"):
                    token = cap_token.strip()
            except Exception:
                pass
        return bool(token and not token.startswith("${"))

    # -----------------------------------------------------------------------------

    def get_github_user(self) -> str:
        """Returns the configured GitHub user handle or default organization."""
        user = os.environ.get("GITHUB_USER", "").strip()
        if not user and hasattr(self.controller, "config") and self.controller.config:
            try:
                cap_user = getattr(self.controller.config, "data", {}).get("capabilities", {}).get("squad_agent", {}).get("github", {}).get("user", "")
                if isinstance(cap_user, str) and not cap_user.startswith("${"):
                    user = cap_user.strip()
            except Exception:
                pass
        return user or "Bastien-Antigravity"

    # -----------------------------------------------------------------------------

    def register_routes(self, app: FastAPI):
        """Registers the REST routes to the FastAPI application."""
        router = APIRouter()

        @router.get("/api/v1/status")
        async def get_status():
            status_info = await self.controller.get_status()
            gh_configured = self.is_github_configured()
            return {
                "healthy": status_info.get("healthy", True) and gh_configured,
                "status": status_info.get("status", "running") if gh_configured else "disabled",
                "version": status_info.get("version", "0.0.1"),
                "timestamp": status_info.get("timestamp", int(time.time())),
                "github_configured": gh_configured,
                "github_user": self.get_github_user()
            }

        @router.get("/api/v1/squad/commands")
        async def get_commands():
            return {
                "success": True,
                "commands": self.controller.list_commands(),
                "timestamp": int(time.time())
            }

        @router.get("/api/v1/squad/active-mode")
        async def get_active_mode():
            mode = await self.controller.get_active_mode()
            mode_details = self.controller.get_mode_details(mode)
            return {
                "success": True,
                "mode": mode,
                "name": mode_details[0],
                "description": mode_details[1],
                "timestamp": int(time.time())
            }

        @router.post("/api/v1/squad/active-mode")
        async def switch_mode(request: Request):
            if not self.is_github_configured():
                raise HTTPException(
                    status_code=403, 
                    detail="Squad Agent is disabled: GITHUB_TOKEN environment variable is not configured."
                )
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")
            
            mode = body.get("mode")
            if not mode:
                raise HTTPException(status_code=400, detail="Missing 'mode' parameter")

            success, msg = await self.controller.switch_mode(str(mode))
            return {
                "success": success,
                "message": msg,
                "timestamp": int(time.time())
            }

        @router.get("/api/v1/squad/run/{cmd_name}")
        async def run_command_stream(cmd_name: str, args: str = ""):
            if not self.is_github_configured():
                raise HTTPException(
                    status_code=403, 
                    detail="Squad Agent is disabled: GITHUB_TOKEN environment variable is not configured."
                )
            # Prevent infinite loop or squad-agent recursion
            if cmd_name == "squad-agent":
                raise HTTPException(status_code=400, detail="Cannot recursively invoke squad-agent daemon.")

            async def event_generator():
                yield f"data: [START] Initiating execution of command: {cmd_name} {args}\n\n"
                
                cmd = [sys.executable, "main.py", cmd_name]
                if args:
                    # Parse args query safely split
                    cmd.extend(args.split())

                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                        cwd=str(self.controller.repo_root)
                    )
                    
                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        decoded_line = line.decode("utf-8", errors="replace").strip()
                        yield f"data: {decoded_line}\n\n"
                        
                    await proc.wait()
                    if proc.returncode == 0:
                        yield "data: [COMPLETE] Command executed successfully.\n\n"
                    else:
                        yield f"data: [FAILED] Command completed with exit code: {proc.returncode}\n\n"
                except Exception as e:
                    yield f"data: [ERROR] Failed to run command: {e}\n\n"

            return StreamingResponse(event_generator(), media_type="text/event-stream")

        @router.get("/api/v1/squad/chat/stream/{session_id}")
        async def stream_chat_messages(session_id: str, request: Request, once: bool = False):
            async def event_generator():
                queue = asyncio.Queue()
                
                async def msg_cb(payload):
                    if payload.get("session_id") == session_id:
                        await queue.put(payload)
                
                event_bus = getattr(self.controller, "event_bus", None)
                if event_bus:
                    import inspect
                    res = event_bus.subscribe("bastien-antigravity.squad.chat", callback=msg_cb)
                    if inspect.isawaitable(res):
                        await res
                else:
                    from src.interfaces import LocalEventBus
                    LocalEventBus.subscribe("bastien-antigravity.squad.chat", msg_cb)
                
                try:
                    yield f"data: {json.dumps({'event': 'connected', 'session_id': session_id})}\n\n"
                    if once:
                        return
                    while True:
                        if await request.is_disconnected():
                            break
                        try:
                            msg_payload = await asyncio.wait_for(queue.get(), timeout=0.1)
                            yield f"data: {json.dumps(msg_payload)}\n\n"
                        except asyncio.TimeoutError:
                            if await request.is_disconnected():
                                break
                            yield ": keep-alive\n\n"
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                finally:
                    pass
                        
            return StreamingResponse(event_generator(), media_type="text/event-stream")

        @router.get("/api/v1/squad/chat/{session_id}")
        async def get_chat_history(session_id: str):
            history = await self.controller.get_chat_history(session_id)
            return {"success": True, "history": history}

        @router.post("/api/v1/squad/chat/{session_id}")
        async def post_chat_message(session_id: str, request: Request):
            if not self.is_github_configured():
                raise HTTPException(
                    status_code=403, 
                    detail="Squad Agent is disabled: GITHUB_TOKEN environment variable is not configured."
                )
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")
            
            message = body.get("message")
            if not message:
                raise HTTPException(status_code=400, detail="Missing 'message' parameter")
            
            await self.controller.publish_user_message(session_id, message)
            return {"success": True, "message": "Message published successfully"}

        app.include_router(router)
