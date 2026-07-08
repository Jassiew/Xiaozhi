"""
多设备模拟器 — 用随机图片伪装多个小智端同时发帧
用于测试多设备绑定和概览功能

用法: python simulate_devices.py [设备数量] [间隔秒数]
示例: python simulate_devices.py 3 2    # 3个设备,每2秒各发一帧
"""

import sys
import time
import httpx
import numpy as np
import cv2

BASE_URL = "http://localhost:8000"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"


def login():
    resp = httpx.post(f"{BASE_URL}/api/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    resp.raise_for_status()
    return resp.json()["access_token"]


def bind_device(token, device_id, name):
    resp = httpx.post(
        f"{BASE_URL}/api/devices/bind",
        json={"device_id": device_id, "name": name, "bind_code": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    if "bind_code" in data:
        print(f"  [{name}] 新绑定成功, 绑定码: {data['bind_code']}")
    else:
        print(f"  [{name}] 已存在或绑定成功")


def make_random_frame(width=320, height=240):
    """生成一张随机彩色图, 模拟摄像头画面"""
    img = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    _, jpeg = cv2.imencode(".jpg", img)
    return jpeg.tobytes()


def send_frame(device_id, jpeg_bytes):
    """向 /upload/frame 发一帧"""
    try:
        files = {"file": ("frame.jpg", jpeg_bytes, "image/jpeg")}
        resp = httpx.post(f"{BASE_URL}/upload/frame?device_id={device_id}", files=files, timeout=5)
        return resp.json().get("status") == "ok"
    except Exception as e:
        print(f"  [{device_id}] 发送失败: {e}")
        return False


def main():
    num_devices = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0

    print(f"=== 多设备模拟器 ===")
    print(f"设备数: {num_devices}, 发送间隔: {interval}s")
    print(f"后端地址: {BASE_URL}")

    # 登录
    print("登录中...")
    try:
        token = login()
        print("登录成功")
    except Exception as e:
        print(f"登录失败: {e}")
        print("请确保后端已启动: python main.py")
        return

    # 使用固定设备ID（同一设备重启后ID不变，避免数据库重复）
    devices = []
    for i in range(num_devices):
        device_id = f"sim-device-{i+1:02d}"
        name = f"模拟设备-{i+1}"
        print(f"绑定设备 [{i+1}/{num_devices}]: {device_id}")
        try:
            bind_device(token, device_id, name)
        except Exception as e:
            print(f"  绑定失败: {e}")
        devices.append((device_id, name))

    print(f"\n开始模拟 {num_devices} 个设备发送帧...")
    print(f"打开浏览器访问 http://localhost:8000 查看概览\n")

    frame_count = 0
    try:
        while True:
            frame_count += 1
            for device_id, name in devices:
                jpeg = make_random_frame()
                ok = send_frame(device_id, jpeg)
                status = "OK" if ok else "FAIL"
                sys.stdout.write(f"\r轮次 {frame_count} | {name}({device_id}) {status}  ")
                sys.stdout.flush()
                time.sleep(0.15)
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n\n已停止, 共发送 {frame_count} 轮")


if __name__ == "__main__":
    main()
