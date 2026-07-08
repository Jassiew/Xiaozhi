# CBPH-Net 集成设计

**日期:** 2026-07-01
**状态:** 已实现 ✅

## 实现总结

- **cbph_inference.py** — 纯 onnxruntime 推理，无需 torch/ultralytics（12MB 依赖 vs 2GB）
- **实测性能**: 12ms/帧（CPU），比设计预期的 18ms 更好
- **analyzer.py** — 改动完成，CBPH-Net 优先，Pose 按需跳过
- **测试**: 15/18 通过（3 个失败 = MySQL 未启动，与改动无关）

---

## 1. 背景与目标

### 当前问题
伴学系统现有 MediaPipe 动作检测不准——`calc_action_state()` 基于 Pose 关键点坐标的硬编码规则判断 writing/reading/listening，对姿态变化敏感，误判率高。

### 目标
集成 CBPH-Net（YOLOv8n，STBD-08 课堂行为数据集训练）替代现有规则型动作检测，同时保留 MediaPipe 的疲劳/生理状态检测能力。

### CBPH-Net 模型信息
- 架构: YOLOv8n（300 万参数）
- 训练尺寸: 480×480
- 推理尺寸: 320×320（优化后，实测 33ms PyTorch / 预计 ~18ms ONNX）
- 8 个原始类别: hand-raising(0), reading(1), writing(2), listening(3), turning_around(4), standing(5), discussing(6), guiding(7)
- 本项目使用: reading(1), writing(2), listening(3), turning_around(4)
- 不启用: standing(5) — 单人场景暂无需求; hand-raising/discussing/guiding — 课堂互动/教师行为

### 拍摄角度要求
CBPH-Net 训练数据为教室监控视角（正面、高位俯拍），**建议小智设备放在学生正前方桌面**。侧面角度会降低 reading/writing 的区分准确度；turning_around 对角度不敏感。

---

## 2. 架构设计

### 融合策略: CBPH-Net（动作） + MediaPipe（生理状态）

```
ESP32 帧 (640×480 JPEG) ──→ ws_handler.py ──→ frame_queue
                                              │
                                              ▼
┌─ analyzer.py ──────────────────────────────────────────┐
│                                                        │
│  1. 解码 BGR, resize 320×320 (CBPH-Net 用)             │
│                      320×240 (MediaPipe 用)            │
│                                                        │
│  2. CBPH-Net ONNX 推理 ──→ (action, confidence)        │
│     classes=[1,2,3,4], conf≥0.4                        │
│                                                        │
│  3. MediaPipe FaceMesh ──→ 疲劳+注视+分心 (始终运行)    │
│                                                        │
│  4. MediaPipe Pose (按需)                               │
│     ├─ CBPH 高置信度 (≥0.5) → 跳过 Pose ✂️ 省 15ms     │
│     └─ CBPH 低置信度 (<0.5) → 运行 Pose (趴桌/玩手机)   │
│                                                        │
│  5. calc_learning_state() ──→ 最终 9 状态之一           │
│                                                        │
│  6. _write_db() → MySQL                                │
│     _build_status_message() → output_queue → 设备       │
└────────────────────────────────────────────────────────┘
```

### CBPH-Net 取代的内容

| 原有方式 | 改为 | 原因 |
|---------|------|------|
| `calc_action_state()` 中 reading/writing/idle 的 Pose 规则判断 | CBPH-Net 直接输出 reading/writing/listening | 模型分类比几何规则准确 |
| 无 turning_around 检测 | CBPH-Net turning_around → distracted_away | 新增转身分心检测 |

### MediaPipe 保留的内容

| 功能 | 原因 |
|------|------|
| 疲劳检测 (EAR/PERCLOS/MAR/哈欠/摇头/眨眼) | CBPH-Net 无此能力 |
| 趴桌检测 (躯干角 <25°) | CBPH-Net 无 lying_down 类别 |
| 玩手机检测 (手腕位置) | CBPH-Net 无此类别 |
| 注视方向 (gaze_direction) | CBPH-Net 无此能力 |
| 人员存在检测 (person_present) | CBPH-Net 不是人脸检测器 |

---

## 3. 状态映射

### CBPH-Net 动作 → learning_state

| CBPH-Net 动作 | 映射状态 | 设备表情 | 屏幕文字 |
|--------------|---------|---------|---------|
| listening | `engaged_screen` | happy | 认真听课中 👍 |
| writing | `engaged_writing` | cool | 正在认真写字 ✍️ |
| reading | `engaged_reading` | relaxed | 专注阅读中 📖 |
| turning_around | `distracted_away` | confused | 注意力分散了 👀 |
| (无检测) | `thinking` | thinking | 思考中... |

### 更新后的学习状态判定优先级

```
1. absent             ← 无人脸 (MediaPipe FaceMesh)
2. resting            ← 躯干角 <25° (MediaPipe Pose, fallback)
3. fatigued           ← fatigue ≥ 0.6 (MediaPipe FaceMesh)
4. distracted_phone   ← 手腕+脸部距离 (MediaPipe Pose)
5. distracted_away    ← CBPH turning_around 或 gaze=away ≥30s
6. engaged_writing    ← CBPH writing (conf ≥0.4)
7. engaged_reading    ← CBPH reading (conf ≥0.4)
8. engaged_screen     ← CBPH listening (conf ≥0.4)
9. thinking           ← 兜底 (CBPH 无检测 + 视线不定)
```

状态切换防抖（2秒）保持现有逻辑不变。

---

## 4. 文件变更清单

### 新增文件

| 文件 | 职责 |
|------|------|
| `cbph_inference.py` | CBPH-Net ONNX 模型加载、推理封装、类别映射 |
| `models/cbph_best.onnx` | 导出的 ONNX 模型文件 |

### 改造文件

| 文件 | 改动内容 |
|------|---------|
| `analyzer.py` | `analyze_frame()` 增加 CBPH-Net 推理步骤；`calc_action_state()` 接受 CBPH 结果作为优先输入，低置信度回退 Pose；按 CBPH 置信度决定是否跳过 Pose |
| `requirements.txt` | 追加 `onnxruntime` |

### 不需要改动的文件

| 文件 | 原因 |
|------|------|
| `ws_handler.py` | 帧接收逻辑不变 |
| `main.py` | 启动流程不变 |
| `db.py` / `models.py` | 数据库 schema 不变 |
| `difficulty.py` | 60s 滑窗逻辑不变（learning_state 名称没变） |
| `api_router.py` | API 不变 |
| ESP32 固件 | 只发帧+收状态，不知道后端换了模型 |

---

## 5. cbph_inference.py 接口设计

```python
# 模块级单例，进程启动时延迟加载一次
_model: YOLO | None = None

CLASS_MAP = {
    1: "reading",
    2: "writing",
    3: "listening",
    4: "turning_around",
}
TARGET_CLASSES = [1, 2, 3, 4]
DEFAULT_CONF = 0.4

def get_model() -> YOLO:
    """延迟加载 ONNX 模型（进程级单例）"""

def infer(frame_bgr: np.ndarray, conf_threshold: float = 0.4) -> tuple[str | None, float]:
    """输入 BGR 图像 (H,W,3)，返回 (action_name, confidence)
    
    action_name: "reading" | "writing" | "listening" | "turning_around" | None
    confidence: 0.0 ~ 1.0
    """
```

### 模型导出（一次性操作，上线前完成）

```bash
# 在 CBPH-Net 项目的 yolo_env 中执行
python -c "
from ultralytics import YOLO
model = YOLO('runs/detect/train-5/weights/best.pt')
model.export(format='onnx', imgsz=320, simplify=True, opset=12)
"
# 输出: runs/detect/train-5/weights/best.onnx
# 复制到: student-monitor/models/cbph_best.onnx
```

---

## 6. analyzer.py 改动要点

### analyze_frame() 增加 CBPH 推理步骤

在 MediaPipe 之前先跑 CBPH-Net:

```python
def analyze_frame(device_id, frame, sscma_data=None, vad_data=None):
    # ...现有 resize + BGR→RGB 逻辑...
    
    # 新增: CBPH-Net 推理
    frame_320 = cv2.resize(frame, (320, 320))
    cbph_action, cbph_conf = cbph_inference.infer(frame_320)
    
    # FaceMesh (始终运行 — 疲劳+注视需要)
    face_results = face_mesh.process(rgb)
    
    # Pose (按 CBPH 置信度决定)
    if cbph_conf >= 0.5:
        pose_results = None       # 跳过 Pose，省 15ms
    else:
        pose_results = pose_model.process(rgb)  # fallback
    
    # 传入 CBPH 结果
    action_state, torso_angle = calc_action_state(
        pose_results, cbph_action, cbph_conf
    )
    # ...其余逻辑不变...
```

### calc_action_state() 签名升级

```python
def calc_action_state(pose_results, 
                      cbph_action: str | None = None, 
                      cbph_conf: float = 0.0) -> tuple[str, float]:
    # CBPH 优先
    if cbph_action and cbph_conf >= 0.4:
        return cbph_action, 90.0   # 默认躯干角度
    
    # 回退: 原有 Pose 规则（趴桌、玩手机、idle）
    return _legacy_action_state(pose_results)
```

---

## 7. 性能预算

| 场景 | CBPH ONNX | FaceMesh | Pose | 合计 | vs 100ms 帧间隔 |
|------|-----------|----------|------|------|----------------|
| CBPH 高置信度 (>50%) | ~18ms | ~20ms | 跳过 | **~38ms** | ✅ 充裕 |
| CBPH 低置信度 (fallback) | ~18ms | ~20ms | ~15ms | **~53ms** | ✅ 充裕 |
| 当前系统 (无 CBPH) | — | ~20ms | ~15ms | ~35ms | ✅ |

---

## 8. 测试计划

### 单元测试
- `cbph_inference.infer()` 返回格式正确性
- 确认 confidence=0.4 阈值下 4 个类别均可触发

### 集成测试
- 用现有测试帧跑一遍新管线，确认无异常
- 对比新旧 `learning_state` 输出差异

### 实际验证
- 运行后端，接入实际设备
- 人工做 reading / writing / listening / turning_around 动作
- 观察设备屏幕 emoji 切换是否正确

---

## 9. 风险与缓解

| 风险 | 可能性 | 缓解 |
|------|--------|------|
| ONNX 推理速度不达预期 (>30ms) | 低 | 可降为 256×256 输入再省 ~7ms |
| CBPH-Net 在侧面角度不准 | 中 | 先用正面，后续采集侧面数据 fine-tune |
| CBPH-Net 把 idle 误判为 listening | 中 | confidence 阈值调高到 0.5，结合 gaze 交叉验证 |
| 无检测时 thinking 兜底太宽泛 | 低 | thinking 状态本身语义宽泛，可接受 |
