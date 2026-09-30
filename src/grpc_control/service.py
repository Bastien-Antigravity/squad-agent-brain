#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Exposes the SquadControlService gRPC endpoints.
Allows external clients to run subcommands, get status, switch modes, and get the active mode.

DATA FLOW:
1. Client issues RPC call to SquadControlService (GetStatus, RunCommand, GetActiveMode, SwitchMode).
2. Servicer invokes CommandController to execute action.
3. Servicer packages result into corresponding Protobuf response message.

KEY PARAMETERS:
- controller: CommandController singleton instance.
- logger: UniLog or compatible logging handle.
- ip: Network bind IP address.
- port: Network bind port number.
"""

import time
import grpc
from src.grpc_control import squad_control_pb2, squad_control_pb2_grpc

# -----------------------------------------------------------------------------

class SquadControlServiceImpl(squad_control_pb2_grpc.SquadControlServiceServicer):
    """Servicer implementation for gRPC Squad Control."""

    # -----------------------------------------------------------------------------

    def __init__(self, controller, logger):
        self.controller = controller
        self.logger = logger

    # -----------------------------------------------------------------------------

    async def GetStatus(self, request, context):
        status = await self.controller.get_status()
        return squad_control_pb2.GetStatusResponse(
            healthy=status.get("healthy", True),
            status=status.get("status", "running"),
            version=status.get("version", "1.0.0"),
            timestamp=status.get("timestamp", int(time.time()))
        )

    # -----------------------------------------------------------------------------

    async def RunCommand(self, request, context):
        try:
            success, message = await self.controller.run_subcommand_async(request.command, request.args)
            return squad_control_pb2.RunCommandResponse(
                success=success,
                message=message,
                timestamp=int(time.time())
            )
        except Exception as e:
            return squad_control_pb2.RunCommandResponse(
                success=False,
                message=str(e),
                timestamp=int(time.time())
            )

    # -----------------------------------------------------------------------------

    async def GetActiveMode(self, request, context):
        mode = await self.controller.get_active_mode()
        return squad_control_pb2.GetActiveModeResponse(
            mode=mode
        )

    # -----------------------------------------------------------------------------

    async def SwitchMode(self, request, context):
        try:
            success, message = await self.controller.switch_mode(request.mode)
            return squad_control_pb2.SwitchModeResponse(
                success=success,
                message=message
            )
        except Exception as e:
            return squad_control_pb2.SwitchModeResponse(
                success=False,
                message=str(e)
            )

# -----------------------------------------------------------------------------

_grpc_server = None

def get_grpc_server():
    global _grpc_server
    return _grpc_server

# -----------------------------------------------------------------------------

async def start_grpc_server(controller, ip, port, logger):
    """Initializes and starts the asynchronous Squad Control gRPC server."""
    global _grpc_server
    _grpc_server = grpc.aio.server()
    squad_control_pb2_grpc.add_SquadControlServiceServicer_to_server(
        SquadControlServiceImpl(controller, logger), _grpc_server
    )
    listen_addr = f"{ip}:{port}"
    bound_port = _grpc_server.add_insecure_port(listen_addr)
    if bound_port == 0:
        logger.error(f"Failed to bind gRPC Squad Control server on {listen_addr}")
        return None
    logger.info(f"Starting gRPC Squad Control server on {listen_addr} (bound port: {bound_port})...")
    await _grpc_server.start()
    return _grpc_server
