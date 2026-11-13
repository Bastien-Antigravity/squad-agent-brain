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
                "github_user": self.get_github_user(),
                "brain_id": status_info.get("brain_id", "obsidian-brain")
            }

        @router.get("/api/v1/contracts")
        async def get_contracts(request: Request):
            from src.rest.contracts import build_squad_agent_contracts
            return build_squad_agent_contracts(app=request.app, config=getattr(self.controller, "config", None))

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
        async def stream_chat_messages(session_id: str, request: Request, once: bool = False, brain_id: str = ""):
            async def event_generator():
                queue = asyncio.Queue()
                
                async def msg_cb(payload):
                    if payload.get("session_id") == session_id:
                        await queue.put(payload)
                
                target_topic = f"bastien-antigravity.{brain_id}.squad.chat" if brain_id and brain_id not in ("obsidian-brain", "root", "main") else "bastien-antigravity.squad.chat"
                event_bus = getattr(self.controller, "event_bus", None)
                nats_subs = []
                if event_bus:
                    import inspect
                    res = event_bus.subscribe(target_topic, callback=msg_cb)
                    if inspect.isawaitable(res):
                        nats_subs = await res
                    else:
                        nats_subs = res
                else:
                    from src.interfaces import LocalEventBus
                    LocalEventBus.subscribe(target_topic, msg_cb)
                
                try:
                    yield f"data: {json.dumps({'event': 'connected', 'session_id': session_id, 'brain_id': brain_id or 'obsidian-brain'})}\n\n"
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
                    if event_bus and hasattr(event_bus, "unsubscribe"):
                        import inspect
                        unsub_res = event_bus.unsubscribe(target_topic, msg_cb, nats_subs)
                        if inspect.isawaitable(unsub_res):
                            await unsub_res
                    else:
                        from src.interfaces import LocalEventBus
                        LocalEventBus.unsubscribe(target_topic, msg_cb)
                        
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
            
            brain_id = body.get("brain_id") or request.query_params.get("brain_id")
            if brain_id:
                await self.controller.publish_user_message(session_id, message, brain_id=brain_id)
            else:
                await self.controller.publish_user_message(session_id, message)
            return {"success": True, "message": "Message published successfully"}

        @router.get("/api/v1/squad/incidents")
        async def list_incidents(limit: int = Query(50, ge=1, le=200)):
            incidents = self.controller.list_incidents(limit=limit)
            return {"success": True, "incidents": incidents, "count": len(incidents)}

        @router.get("/api/v1/squad/incidents/{incident_id}")
        async def get_incident(incident_id: str):
            incident = self.controller.get_incident(incident_id)
            if not incident:
                raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
            return {"success": True, "incident": incident}

        def require_github() -> None:
            if not self.is_github_configured():
                raise HTTPException(
                    status_code=403,
                    detail="Squad Agent is disabled: GITHUB_TOKEN environment variable is not configured.",
                )

        async def read_json_dict(request: Request, *, required: bool = False) -> dict:
            raw = await request.body()
            if not raw or not raw.strip():
                if required:
                    raise HTTPException(status_code=400, detail="Invalid JSON body")
                return {}
            try:
                body = await request.json()
            except ValueError as exc:
                if required:
                    raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
                return {}
            if not isinstance(body, dict):
                if required:
                    raise HTTPException(status_code=400, detail="Invalid JSON body")
                return {}
            return body

        @router.post("/api/v1/squad/incidents/{incident_id}/approve")
        async def approve_incident(incident_id: str):
            require_github()
            ok, result = await self.controller.approve_incident(incident_id)
            if not ok and "not found" in str(result.get("error", "")).lower():
                raise HTTPException(status_code=404, detail=result["error"])
            return {"success": ok, "incident": result}

        @router.post("/api/v1/squad/incidents/{incident_id}/reject")
        async def reject_incident(incident_id: str, request: Request):
            require_github()
            body = await read_json_dict(request)
            reason = str(body.get("reason") or "")
            ok, result = await self.controller.reject_incident(incident_id, reason=reason)
            if not ok and "not found" in str(result.get("error", "")).lower():
                raise HTTPException(status_code=404, detail=result["error"])
            return {"success": ok, "incident": result}

        @router.post("/api/v1/squad/incidents/{incident_id}/resolve")
        async def resolve_incident(incident_id: str, request: Request):
            require_github()
            body = await read_json_dict(request)
            note = str(body.get("note") or "")
            ok, result = await self.controller.resolve_incident(incident_id, note=note)
            if not ok and "not found" in str(result.get("error", "")).lower():
                raise HTTPException(status_code=404, detail=result["error"])
            return {"success": ok, "incident": result}

        @router.get("/api/v1/squad/autorepair/status")
        async def get_autorepair_status():
            status = self.controller.get_autorepair_status()
            return {"success": True, **status}

        @router.post("/api/v1/squad/autorepair/toggle")
        async def toggle_autorepair(request: Request):
            require_github()
            body = await read_json_dict(request, required=True)
            if not isinstance(body.get("enabled"), bool):
                raise HTTPException(status_code=400, detail="Missing boolean 'enabled' parameter")
            reason = str(body.get("reason") or "")
            auto_apply = body.get("auto_apply")
            if auto_apply is not None and not isinstance(auto_apply, bool):
                raise HTTPException(status_code=400, detail="Optional 'auto_apply' must be boolean")
            status = self.controller.set_autorepair_enabled(body["enabled"], reason=reason, auto_apply=auto_apply)
            if "error" in status:
                raise HTTPException(status_code=503, detail=status["error"])
            return {"success": True, **status}

        @router.post("/api/v1/squad/autorepair/unfreeze")
        async def unfreeze_autorepair_service(request: Request):
            require_github()
            body = await read_json_dict(request, required=True)
            svc = str(body.get("service_name") or "").strip()
            if not svc:
                raise HTTPException(status_code=400, detail="Missing 'service_name' parameter")
            brain_id = body.get("brain_id")
            res = self.controller.unfreeze_autorepair_service(svc, brain_id=brain_id)
            if "error" in res:
                raise HTTPException(status_code=503, detail=res["error"])
            return {"success": True, **res}

        app.include_router(router)
