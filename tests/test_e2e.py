"""端到端测试：模拟设备→后端→API查询完整链路"""
import asyncio
import json
import websockets
import httpx

SERVER = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/device?device_id=e2e-test-01"
DEVICE_ID = "e2e-test-01"

async def test_e2e():
    """完整端到端流程测试"""
    errors = []

    # Step 1: 管理员登录
    async with httpx.AsyncClient(base_url=SERVER) as client:
        resp = await client.post("/api/login",
            json={"username": "admin", "password": "admin123"})
        if resp.status_code != 200:
            errors.append(f"Login failed: {resp.status_code} {resp.text}")
            print(f"\n  FAIL 登录失败: {resp.status_code}")
            return errors
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("  ✓ 管理员登录成功")

        # Step 2: 绑定设备
        resp = await client.post("/api/devices/bind",
            json={"device_id": DEVICE_ID, "name": "e2e测试设备"},
            headers=headers)
        if resp.status_code != 200:
            errors.append(f"Bind failed: {resp.status_code} {resp.text}")
            print(f"\n  FAIL 设备绑定失败: {resp.status_code}")
            return errors
        print("  ✓ 设备绑定成功")

    # Step 3: 模拟设备发送15帧
    jpeg_1px = "R0lGODlhAQABAAAAACwAAAAAAQABAAACAkQBADs="
    try:
        async with websockets.connect(WS_URL) as ws:
            for i in range(15):
                frame = {
                    "type": "frame",
                    "device_id": DEVICE_ID,
                    "timestamp": int(asyncio.get_event_loop().time()),
                    "image": jpeg_1px,
                }
                await ws.send(json.dumps(frame))
                resp = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(resp)
                if data.get("status") != "ok":
                    errors.append(f"Frame {i} not ok: {data}")
        print("  ✓ 设备发送15帧成功")
    except Exception as e:
        errors.append(f"WebSocket failed: {e}")
        print(f"\n  FAIL WebSocket连接/发送失败: {e}")
        return errors

    # Step 4: 等待分析完成
    await asyncio.sleep(3)
    print("  ✓ 等待分析完成")

    # Step 5: 查询实时数据
    async with httpx.AsyncClient(base_url=SERVER) as client:
        resp = await client.get(f"/api/realtime/{DEVICE_ID}", headers=headers)
        if resp.status_code != 200:
            errors.append(f"Realtime query failed: {resp.status_code}")
            print(f"\n  FAIL 实时查询失败: {resp.status_code}")
            return errors
        data = resp.json()
        if not data.get("online"):
            errors.append("Device shows offline")
            print(f"\n  FAIL 设备显示离线")
            return errors
        summary = data.get("summary", {})
        print(f"  ✓ 实时数据: fatigue={summary.get('avg_fatigue', 'N/A')}, "
              f"distraction={summary.get('avg_distraction', 'N/A')}, "
              f"difficulty={summary.get('avg_difficulty', 'N/A')}")

        # Step 6: 查询时段列表
        resp = await client.get(f"/api/sessions?device_id={DEVICE_ID}", headers=headers)
        if resp.status_code != 200:
            errors.append(f"Sessions query failed: {resp.status_code}")
            print(f"\n  FAIL 时段查询失败: {resp.status_code}")
            return errors
        sessions = resp.json()
        if len(sessions) == 0:
            errors.append("No sessions found")
            print(f"\n  FAIL 无学习时段记录")
            return errors
        print(f"  ✓ 时段列表: {len(sessions)}条")

        # Step 7: 查询时段详情
        session_id = sessions[0]["id"]
        resp = await client.get(f"/api/sessions/{session_id}", headers=headers)
        if resp.status_code != 200:
            errors.append(f"Session detail failed: {resp.status_code}")
            print(f"\n  FAIL 时段详情查询失败: {resp.status_code}")
            return errors
        detail = resp.json()
        if detail.get("total_records", 0) == 0:
            errors.append("No analysis records")
            print(f"\n  FAIL 无分析记录")
            return errors
        print(f"  ✓ 时段详情: {detail['total_records']}条分析记录")

    if not errors:
        print("\n  ✓ 端到端测试全部通过！")
    else:
        print(f"\n  FAIL {len(errors)}个错误: {errors}")

    return errors


if __name__ == "__main__":
    errors = asyncio.run(test_e2e())
    if errors:
        exit(1)
