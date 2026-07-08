import asyncio
import json
import pytest
import websockets

@pytest.mark.asyncio
async def test_device_connect_and_send_frame():
    """验证WebSocket端点能接收设备帧"""
    async with websockets.connect("ws://localhost:8000/ws/device?device_id=test-dev-01") as ws:
        frame = {
            "type": "frame",
            "device_id": "test-dev-01",
            "timestamp": 1716000000,
            "image": "R0lGODlhAQABAAAAACwAAAAAAQABAAACAkQBADs="
        }
        await ws.send(json.dumps(frame))
        resp = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(resp)
        assert data["status"] == "ok"
