import asyncio
import base64
import json
import os
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Request
import cv2
import numpy as np
from config import FRAME_SAVE_DIR, QUEUE_MAXSIZE
from db import get_connection
from crypto_utils import decrypt_frame, try_decrypt

router = APIRouter()

frame_queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
output_queue: asyncio.Queue = None  # Set by main.py, analyzer writes results here

_device_ws = {}  # device_id -> WebSocket


async def _broadcast_results():
    """从 output_queue 读取分析结果，推送给对应设备"""
    while True:
        try:
            msg = await asyncio.wait_for(output_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        device_id = msg.pop("device_id", None)
        ws = _device_ws.get(device_id)
        if ws:
            try:
                await ws.send_json(msg)
            except Exception:
                _device_ws.pop(device_id, None)


def _ensure_device(device_id):
    """Auto-register unknown devices so they appear in dashboard without manual binding"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM devices WHERE device_id = %s", (device_id,))
            if cur.fetchone() is None:
                cur.execute(
                    "INSERT INTO devices (device_id, name, bind_code) VALUES (%s, %s, %s)",
                    (device_id, device_id, ""),
                )
                conn.commit()
    finally:
        conn.close()


def _process_frame(jpeg_bytes, device_id, timestamp=None, sscma_data=None, vad_data=None):
    """公共帧处理：存文件 + 入分析队列"""
    now = datetime.now()
    date_dir = os.path.join(FRAME_SAVE_DIR, now.strftime("%Y-%m-%d"))
    os.makedirs(date_dir, exist_ok=True)
    ts = timestamp or int(now.timestamp())
    safe_id = device_id.replace(":", "-")
    filename = f"{now.strftime('%H%M%S')}_{safe_id}_{ts}.jpg"
    filepath = os.path.join(date_dir, filename)
    with open(filepath, "wb") as f:
        f.write(jpeg_bytes)

    frame_array = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
    if frame_array is None:
        return False

    payload = {
        "device_id": device_id,
        "timestamp": ts,
        "image": frame_array,
        "filepath": filepath,
    }
    if sscma_data:
        payload["sscma"] = sscma_data
    if vad_data:
        payload["vad"] = vad_data

    try:
        frame_queue.put_nowait(payload)
    except asyncio.QueueFull:
        pass
    return True

@router.websocket("/ws/device")
async def device_websocket(ws: WebSocket, device_id: str = Query(...)):
    await ws.accept()
    _device_ws[device_id] = ws
    print(f"[WS] {device_id} connected")
    frame_count = 0

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"status": "ok", "type": "pong"}))
                continue

            frame_b64 = msg["image"]
            timestamp = msg.get("timestamp")
            device_id_msg = msg.get("device_id", device_id)
            sscma_data = msg.get("sscma")
            vad_data = msg.get("vad")
            _ensure_device(device_id_msg)
            raw_data = base64.b64decode(frame_b64)
            # Decrypt if the frame was encrypted on the ESP32
            if msg.get("encrypted"):
                jpeg_bytes = decrypt_frame(raw_data)
            else:
                jpeg_bytes = raw_data
            _process_frame(jpeg_bytes, device_id_msg, timestamp, sscma_data, vad_data)
            await ws.send_text(json.dumps({"status": "ok"}))
            frame_count += 1
            if frame_count % 30 == 0:
                print(f"[WS] {device_id}: {frame_count} frames received")

    except WebSocketDisconnect:
        print(f"[WS] {device_id} disconnected normally ({frame_count} frames)")
    except OSError as e:
        print(f"[WS] {device_id} OSError (WiFi dropped?): {e}")
    except Exception as e:
        print(f"[WS] {device_id} unexpected error: {type(e).__name__}: {e}")
    finally:
        _device_ws.pop(device_id, None)
        print(f"[WS] {device_id} cleaned up")


@router.post("/upload/frame")
async def upload_frame(request: Request, device_id: str = "watcher-01"):
    """小智 Watcher HTTP 上传端点 — 手动解析 multipart，兼容 chunked 传输"""
    content_type = request.headers.get("content-type", "")
    raw_body = await request.body()

    # 从 Content-Type 提取 boundary
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("boundary="):
            boundary = part.split("=", 1)[1].strip().strip('"')
            break

    if not boundary:
        # 无 boundary，尝试直接当 JPEG 处理（自动检测是否加密）
        _ensure_device(device_id)
        ok = _process_frame(try_decrypt(raw_body), device_id)
        return {"status": "ok" if ok else "error"}

    # 手动解析 multipart: 用 boundary 切分，找到 file 字段的二进制内容
    boundary_bytes = boundary.encode("utf-8")
    delimiter = b"--" + boundary_bytes
    parts = raw_body.split(delimiter)

    jpeg_bytes = None
    is_encrypted = False
    for part_bytes in parts:
        if b"Content-Disposition" not in part_bytes:
            continue
        # 分离 header 和 body（以 \r\n\r\n 为界）
        header_end = part_bytes.find(b"\r\n\r\n")
        if header_end < 0:
            continue
        headers_block = part_bytes[:header_end].decode("utf-8", errors="ignore")
        body = part_bytes[header_end + 4:]

        # 去掉末尾的 \r\n（如果有）
        if body.endswith(b"\r\n"):
            body = body[:-2]

        if 'name="file"' in headers_block and body:
            jpeg_bytes = body
            # 检查 ESP32 固件设置的加密标志
            if "X-Encrypted: 1" in headers_block or "x-encrypted: 1" in headers_block.lower():
                is_encrypted = True
            break

    if not jpeg_bytes:
        return {"status": "error", "message": "no file part found"}

    _ensure_device(device_id)
    if is_encrypted:
        jpeg_bytes = decrypt_frame(jpeg_bytes)
    ok = _process_frame(jpeg_bytes, device_id)
    return {"status": "ok" if ok else "error"}
