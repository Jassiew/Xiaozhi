# 小智屏幕交互设计方案

## 概述

当前小智 ESP32 设备仅单向发送摄像头帧到后端，屏幕交互能力未被利用。本方案将分析结果回传至设备，实现丰富的屏幕表情、文字提醒和语音交互。

## 数据流架构

```
ESP32 摄像头 ──帧(WebSocket)──▶ 后端 analysis ──learning_status(WebSocket)──▶ ESP32 屏幕 + 语音
                                      │
                                    MySQL
```

### 消息格式

后端 → ESP32 新增 `learning_status` 类型消息：

```json
{
  "type": "learning_status",
  "learning_state": "distracted_phone",
  "fatigue_level": 0.12,
  "distraction_level": 0.72,
  "difficulty_indicator": 0.35,
  "message": "别玩手机啦！",
  "emotion": "shocked",
  "alert": "voice"
}
```

| 字段 | 说明 |
|------|------|
| `type` | 固定 `"learning_status"` |
| `learning_state` | 9 种学习状态之一 |
| `fatigue_level` | 疲劳度 0.0~1.0 |
| `distraction_level` | 分心度 0.0~1.0 |
| `difficulty_indicator` | 困难度 0.0~1.0 |
| `message` | 屏幕显示文字 |
| `emotion` | 对应 ESP32 Twemoji 表情名 |
| `alert` | `"voice"` 触发语音 / `"silent"` 仅屏幕 / `null` 无提醒 |

## 学习状态 → 交互映射

| 学习状态 | Emoji | 屏幕文字 | 语音提醒 | 触发条件 |
|----------|-------|---------|---------|---------|
| `engaged_screen` | happy | 认真听课中 👍 | — | — |
| `engaged_writing` | cool | 正在认真写字 ✍️ | — | — |
| `engaged_reading` | relaxed | 专注阅读中 📖 | — | — |
| `thinking` | thinking | 思考中... | — | — |
| `distracted_phone` | shocked | 别玩手机啦！📱 | "请放下手机，专注学习" | 首次触发 |
| `distracted_away` | confused | 注意力分散了 👀 | "请集中注意力哦" | 持续 10s |
| `fatigued` | sleepy | 你看起来有点累 😴 | "休息一下吧，起来走走" | 持续 10s |
| `resting` | sleepy | 正在休息... | — | — |
| `absent` | neutral | 小智等你回来~ | — | — |

## 防骚扰机制

- 同类型语音提醒间隔 ≥ 60 秒
- 分心/疲劳需持续 10 秒才触发语音（防止误报）
- 恢复正常学习后，显示鼓励文字"继续加油！💪"（持续 3 秒后恢复常规显示）

## ESP32 可用 Emoji 列表

Twemoji32/64 表情集合：`neutral`, `happy`, `laughing`, `funny`, `sad`, `angry`, `crying`, `loving`, `embarrassed`, `surprised`, `shocked`, `thinking`, `winking`, `cool`, `relaxed`, `delicious`, `kissy`, `confident`, `sleepy`, `silly`, `confused`

---

## 实现详情

### 后端 — `analyzer.py`

**新增函数 `_build_status_message()`**（第 509–533 行）：

将学习状态映射为设备端所需的表情名、屏幕文字和语音触发标识。映射表见上文「学习状态 → 交互映射」。

```python
def _build_status_message(result: dict) -> dict:
    state = result.get("learning_state", "")
    mapping = {
        "engaged_screen":   ("happy",    "认真听课中 👍",      None),
        "engaged_writing":  ("cool",     "正在认真写字 ✍️",    None),
        "engaged_reading":  ("relaxed",  "专注阅读中 📖",      None),
        "thinking":         ("thinking", "思考中...",         None),
        "distracted_phone": ("shocked",  "别玩手机啦！📱",     "voice"),
        "distracted_away":  ("confused", "注意力分散了 👀",    "voice"),
        "fatigued":         ("sleepy",   "你看起来有点累 😴",  "voice"),
        "resting":          ("sleepy",   "正在休息...",       None),
        "absent":           ("neutral",  "小智等你回来~",     None),
    }
    emotion, message, alert = mapping.get(state, ("neutral", "", None))
    return {
        "type": "learning_status",
        "learning_state": state,
        "fatigue_level": result.get("fatigue_level", 0),
        "distraction_level": result.get("distraction_level", 0),
        "difficulty_indicator": result.get("difficulty_indicator", 0),
        "message": message,
        "emotion": emotion,
        "alert": alert,
    }
```

**修改 `run_analyzer()`**（第 536 行）：新增 `output_queue` 参数，每帧分析完成后调用 `_build_status_message()` 并 `put_nowait` 推入队列。

```python
async def run_analyzer(frame_queue: asyncio.Queue, output_queue: asyncio.Queue = None):
    ...
    # 推送分析结果到设备（用于屏幕交互）
    if output_queue is not None:
        status_msg = _build_status_message(result)
        status_msg["device_id"] = device_id
        try:
            output_queue.put_nowait(status_msg)
        except asyncio.QueueFull:
            pass
```

### 后端 — `ws_handler.py`

**新增变量**（第 15–17 行）：

```python
output_queue: asyncio.Queue = None  # Set by main.py
_device_ws = {}  # device_id -> WebSocket
```

**新增协程 `_broadcast_results()`**（第 20–31 行）：从 `output_queue` 读取结果，查找对应设备的 WebSocket 并推送，连接断开时自动清理。

```python
async def _broadcast_results():
    while True:
        msg = await asyncio.wait_for(output_queue.get(), timeout=1.0)
        device_id = msg.pop("device_id", None)
        ws = _device_ws.get(device_id)
        if ws:
            await ws.send_json(msg)
```

**修改 `device_websocket()`**（第 60–100 行）：连接时注册 `_device_ws[device_id] = ws`，断开时 `finally` 块中清理 `_device_ws.pop(device_id, None)`。

### 后端 — `main.py`

**修改 `lifespan()`**（第 11–38 行）：创建 `output_queue`（maxsize=100），启动 `_broadcast_results` 后台任务，传入 `run_analyzer`。shutdown 时取消两个任务。

```python
ws_handler.output_queue = asyncio.Queue(maxsize=100)
broadcast_task = asyncio.create_task(ws_handler._broadcast_results())
analyzer_task = asyncio.create_task(
    run_analyzer(frame_queue, ws_handler.output_queue)
)
```

### ESP32 — `student_monitor.cc`

**新增回调 `OnMonitorWsData()`**（第 61–89 行）：WebSocket 接收回调，解析 `learning_status` JSON，调用显示 API 更新屏幕。

```cpp
static void OnMonitorWsData(const char* data, size_t len, bool binary) {
    if (binary) return;
    cJSON* root = cJSON_Parse(std::string(data, len).c_str());
    if (!root) return;

    cJSON* type = cJSON_GetObjectItem(root, "type");
    if (type && strcmp(type->valuestring, "learning_status") == 0) {
        auto display = Board::GetInstance().GetDisplay();
        if (display) {
            cJSON* emotion = cJSON_GetObjectItem(root, "emotion");
            cJSON* message = cJSON_GetObjectItem(root, "message");
            cJSON* learning_state = cJSON_GetObjectItem(root, "learning_state");
            if (emotion && cJSON_IsString(emotion))
                display->SetEmotion(emotion->valuestring);
            if (message && cJSON_IsString(message))
                display->SetChatMessage("system", message->valuestring);
            if (learning_state && cJSON_IsString(learning_state))
                display->SetStatus(learning_state->valuestring);
        }
    }
    cJSON_Delete(root);
}
```

**注册回调**（第 108 行）：在 WebSocket 连接成功后调用 `ws->OnData(OnMonitorWsData)`。

**待实现**：语音提醒功能。当前 `alert: "voice"` 消息被 ESP32 忽略，后续需接入 `Application::Alert()` 或 `AudioService::PlaySound()` 播放内置 OGG 提示音。

---

## 屏幕效果示意

```
正常学习时：              分心时：                  疲劳时：
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│   😊         │        │   😱         │        │   😴         │
│              │        │              │        │              │
│ 认真听课中 👍 │        │ 别玩手机啦！📱 │        │ 你累了 😴    │
│              │        │              │        │              │
└──────────────┘        └──────────────┘        └──────────────┘
                        🔊 "请放下手机，       🔊 "休息一下吧，
                           专注学习"              起来走走"
```
