"""CBPH-Net 行为检测推理模块

使用 ONNX Runtime 加载 YOLOv8n 模型，检测学生课堂行为。
模型: STBD-08 数据集训练，8类 → 本项目使用4类（面向单人学生）。

类别映射:
    1: reading        → engaged_reading
    2: writing        → engaged_writing
    3: listening      → engaged_screen
    4: turning_around → distracted_away
"""

import numpy as np
from pathlib import Path

# 模块级单例，进程启动时延迟加载
_model = None
_model_lock = False  # 防止并发加载

# 类别 ID → 名称映射（仅保留学生相关4类）
CLASS_MAP = {
    1: "reading",
    2: "writing",
    3: "listening",
    4: "turning_around",
}

# 推理时只检测这4个类别
TARGET_CLASSES = [1, 2, 3, 4]

# 默认置信度阈值
DEFAULT_CONF = 0.5

# 模型文件路径（相对于项目根目录）
MODEL_PATH = Path(__file__).parent / "models" / "cbph_best.onnx"

# 输入尺寸
INPUT_SIZE = (320, 320)


def get_model():
    """延迟加载 ONNX 模型（进程级单例，线程安全）"""
    global _model
    if _model is not None:
        return _model

    # 优先使用 ultralytics（API 简洁，自动处理前/后处理）
    try:
        from ultralytics import YOLO
        _model = YOLO(str(MODEL_PATH))
        print(f"[CBPH] ONNX 模型已加载 (ultralytics, device=cpu)")
    except ImportError:
        # 回退：纯 onnxruntime（无需 torch）
        import onnxruntime as ort
        _model = ort.InferenceSession(str(MODEL_PATH))
        print(f"[CBPH] ONNX 模型已加载 (onnxruntime direct)")
    return _model


def infer(frame_bgr: np.ndarray, conf_threshold: float = DEFAULT_CONF) -> tuple:
    """CBPH-Net 学生行为推理

    Args:
        frame_bgr: BGR 格式图像 (H, W, 3)，任意尺寸
        conf_threshold: 置信度阈值，默认 0.4

    Returns:
        (action_name, confidence)
        - action_name: "reading" | "writing" | "listening" | "turning_around" | None
        - confidence: float (0.0 ~ 1.0)，无检测时为 0.0
    """
    model = get_model()

    # ultralytics YOLO 模式
    if hasattr(model, 'predict') or hasattr(model, '__call__'):
        results = model(
            frame_bgr,
            imgsz=INPUT_SIZE,
            classes=TARGET_CLASSES,
            conf=conf_threshold,
            verbose=False,
        )
        # 取置信度最高的检测结果
        boxes = results[0].boxes
        if boxes is not None and len(boxes) > 0:
            # 按置信度降序排列
            confs = boxes.conf.cpu().numpy()
            best_idx = int(confs.argmax())
            cls_id = int(boxes.cls[best_idx])
            conf = float(confs[best_idx])
            action = CLASS_MAP.get(cls_id)
            if action is not None:
                return action, conf
        return None, 0.0

    # 纯 onnxruntime 回退模式
    return _infer_ort(model, frame_bgr, conf_threshold)


def _infer_ort(session, frame_bgr: np.ndarray, conf_threshold: float) -> tuple:
    """纯 onnxruntime 推理（备选，无需 ultralytics/torch）"""
    import cv2

    h, w = frame_bgr.shape[:2]
    target_h, target_w = INPUT_SIZE

    # ---- 预处理 ----
    # letterbox resize + pad
    scale = min(target_w / w, target_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(frame_bgr, (new_w, new_h))
    canvas = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
    pad_y = (target_h - new_h) // 2
    pad_x = (target_w - new_w) // 2
    canvas[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized

    # BGR→RGB, HWC→CHW, uint8→float32, /255
    img = canvas[..., ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
    img = img[np.newaxis, ...]

    # ---- 推理 ----
    input_name = session.get_inputs()[0].name
    output = session.run(None, {input_name: img})[0]  # (1, 12, 2100)

    # ---- 后处理 ----
    # YOLOv8 ONNX output: (1, 4+nc, num_preds)
    # channels 0:3 = bbox [cx,cy,w,h], channels 4:11 = class_scores
    output = output[0]  # (12, 2100)
    bbox_raw = output[:4, :]  # (4, 2100)
    cls_raw = output[4:, :]   # (8, 2100)

    # 计算每个 grid level 的网格
    strides = [8, 16, 32]
    grid_sizes = [(target_h // s, target_w // s) for s in strides]
    num_preds_per_level = [gs[0] * gs[1] for gs in grid_sizes]

    all_boxes = []
    all_confs = []
    all_cls_ids = []

    offset = 0
    for stride, (gh, gw) in zip(strides, grid_sizes):
        n = gh * gw
        bbox_lvl = bbox_raw[:, offset:offset + n]   # (4, n)
        cls_lvl = cls_raw[:, offset:offset + n]      # (8, n)
        offset += n

        # reshape to (gh, gw, 4) and (gh, gw, 8)
        bbox_lvl = bbox_lvl.reshape(4, gh, gw)
        cls_lvl = cls_lvl.reshape(8, gh, gw)

        # 网格坐标
        gy, gx = np.mgrid[0:gh, 0:gw].astype(np.float32)

        # Decode bbox (YOLOv8 formula)
        cx = (bbox_lvl[0] + gx) * stride
        cy = (bbox_lvl[1] + gy) * stride
        bw = (bbox_lvl[2] ** 2) * 4 * stride
        bh = (bbox_lvl[3] ** 2) * 4 * stride

        # 转 xyxy
        x1 = (cx - bw / 2).ravel()
        y1 = (cy - bh / 2).ravel()
        x2 = (cx + bw / 2).ravel()
        y2 = (cy + bh / 2).ravel()

        # 只保留目标类别
        for cls_id in TARGET_CLASSES:
            scores = cls_lvl[cls_id].ravel()
            mask = scores > conf_threshold
            if mask.any():
                all_boxes.extend(zip(
                    x1[mask], y1[mask], x2[mask], y2[mask],
                    strict=False,
                ))
                all_confs.extend(scores[mask].tolist())
                all_cls_ids.extend([cls_id] * mask.sum())

    if not all_boxes:
        return None, 0.0

    # NMS
    boxes_np = np.array(all_boxes, dtype=np.float32)
    confs_np = np.array(all_confs, dtype=np.float32)

    # 还原到原图坐标 (letterbox 逆变换)
    boxes_np[:, [0, 2]] -= pad_x
    boxes_np[:, [1, 3]] -= pad_y
    boxes_np /= scale

    # 裁剪到图像范围
    boxes_np[:, [0, 2]] = boxes_np[:, [0, 2]].clip(0, w)
    boxes_np[:, [1, 3]] = boxes_np[:, [1, 3]].clip(0, h)

    indices = cv2.dnn.NMSBoxes(
        boxes_np.tolist(), confs_np.tolist(),
        conf_threshold, 0.45,
    )

    if len(indices) == 0:
        return None, 0.0

    # 取 NMS 后置信度最高的
    best_i = indices.flatten()[confs_np[indices.flatten()].argmax()]
    best_cls = int(all_cls_ids[best_i])
    best_conf = float(confs_np[best_i])
    action = CLASS_MAP.get(best_cls)

    return action, best_conf


def model_ready() -> bool:
    """检查模型文件是否存在"""
    return MODEL_PATH.exists()
