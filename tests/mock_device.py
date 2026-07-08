"""模拟设备：读取本地图片，按800ms间隔通过WebSocket发送到后端"""
import asyncio
import base64
import json
import time
import websockets
import sys

async def mock_device(server_url: str, device_id: str, image_path: str, count: int = 10):
    with open(image_path, "rb") as f:
        jpeg_bytes = f.read()
    image_b64 = base64.b64encode(jpeg_bytes).decode()

    async with websockets.connect(f"{server_url}/ws/device?device_id={device_id}") as ws:
        for i in range(count):
            frame = {
                "type": "frame",
                "device_id": device_id,
                "timestamp": int(time.time()),
                "image": image_b64,
            }
            await ws.send(json.dumps(frame))
            resp = await asyncio.wait_for(ws.recv(), timeout=5)
            print(f"[{i+1}/{count}] Response: {resp}")
            await asyncio.sleep(0.8)

        print("发送完毕，验证数据...")

if __name__ == "__main__":
    server_url = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000"
    device_id = sys.argv[2] if len(sys.argv) > 2 else "mock-001"
    image_path = sys.argv[3] if len(sys.argv) > 3 else "tests/test_frame.jpg"
    count = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    asyncio.run(mock_device(server_url, device_id, image_path, count))
