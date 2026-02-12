"""WebSocket endpoint for real-time notifications."""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# Connected WebSocket clients
connected_clients: list[WebSocket] = []


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket connection for live updates."""
    await ws.accept()
    connected_clients.append(ws)
    logger.info(f"WebSocket client connected. Total: {len(connected_clients)}")

    try:
        while True:
            # Keep connection alive; client can send pings
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"event":"pong"}')
    except WebSocketDisconnect:
        connected_clients.remove(ws)
        logger.info(f"WebSocket client disconnected. Total: {len(connected_clients)}")
    except Exception:
        if ws in connected_clients:
            connected_clients.remove(ws)


async def broadcast(event: str, data: dict = None):
    """Broadcast an event to all connected WebSocket clients."""
    import json
    from datetime import datetime

    message = json.dumps({
        "event": event,
        "data": data or {},
        "timestamp": datetime.utcnow().isoformat(),
    })

    disconnected = []
    for client in connected_clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.append(client)

    for client in disconnected:
        if client in connected_clients:
            connected_clients.remove(client)
