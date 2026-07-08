"""算法分析层：CBPH-Net 动作检测 + MediaPipe 生理状态分析

- 动作检测：CBPH-Net (YOLOv8n ONNX) — reading/writing/listening/turning_around
- 疲劳检测：多指标融合（EAR + PERCLOS + MAR哈欠 + 头部点头 + 眨眼频率）
- 分心检测：头部姿态欧拉角 + CBPH-Net turning_around
- 学习状态：CBPH 动作 + MediaPipe 疲劳/注视融合分类器
- 困难度：60秒滑窗综合
"""

import asyncio
import os
import numpy as np
import cv2
import mediapipe as mp
from datetime import datetime, timezone
from collections import deque
from db import get_connection
from cbph_inference import infer as cbph_infer, model_ready as cbph_ready
from agent import push_behavior

# ============================================================
# MediaPipe 全局初始化（加载一次）
# ============================================================

mp_face_mesh = mp.solutions.face_mesh
mp_pose = mp.solutions.pose

face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

pose_model = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=1,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

print("[Analyzer] MediaPipe FaceMesh + Pose 模型已加载")

# ============================================================
# 关键点索引
# ============================================================

# 眼部（FaceMesh 468点）
LEFT_EYE  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# 嘴部（FaceMesh 468点）— 用于 MAR 哈欠检测
MOUTH_TOP    = 13    # 上唇内缘中点
MOUTH_BOTTOM = 14    # 下唇内缘中点
MOUTH_LEFT   = 78    # 左嘴角内缘
MOUTH_RIGHT  = 308   # 右嘴角内缘

# 几何法头部姿态：只用鼻尖+双眼，不依赖相机内参、不受面部轮廓不稳影响

# ============================================================
# 阈值常量
# ============================================================

# ---- Fatigue constants ----
EAR_CALIB_FRAMES      = 60     # 个人EAR基线标定所需帧数
EAR_CLOSURE_RATIO     = 0.75   # EAR < baseline*0.75 = 闭眼中
EAR_FULLY_CLOSED      = 0.55   # EAR < baseline*0.55 = 完全闭合
PERCLOS_WINDOW_S      = 60     # PERCLOS 统计窗口（秒）
MAR_YAWN_RATIO        = 1.5    # MAR > baseline*1.5 = 哈欠
MAR_YAWN_ABS          = 0.50   # 哈欠的绝对MAR下限
FATIGUE_EMA_ALPHA     = 0.18   # 疲劳平滑系数（越小越平滑）
FATIGUE_DECAY_RATE    = 0.04   # 每帧疲劳自然衰减（eyes open时）
NOD_PITCH_DROP        = 8.0    # 头部点头：pitch下降度数
NOD_RECOVERY_S        = 1.5    # 点头恢复时间上限
THINKING_MAX_S        = 30     # 走神超过此秒数=分心
NOD_RECOVERY_S   = 1.5    # 点头恢复时间上限

# ============================================================
# 每设备独立状态（修复全局变量bug，支持多设备并行）
# ============================================================

_device_states = {}

CALIBRATION_SAMPLES = 100  # ~10s at 10fps

def _get_state(device_id: str) -> dict:
    if device_id not in _device_states:
        _device_states[device_id] = {
            'ear_history':      deque(maxlen=200),    # EAR波形
            'ear_calib_samples':deque(maxlen=EAR_CALIB_FRAMES),  # 基线标定采样
            'ear_baseline':     None,                 # 个人EAR基线（标定后设定）
            'mar_baseline':     None,                 # 个人MAR基线
            'smoothed_fatigue': 0.0,                  # EMA平滑后的疲劳值
            'closed_since':     None,                 # 当前闭眼开始时间(UTC)
            'closed_duration':  0.0,                  # 当前闭眼持续秒数
            'perclos_window':   deque(maxlen=600),    # 60s闭眼状态记录
            'pitch_history':    deque(maxlen=40),     # ~4s pitch波形
            'blink_timestamps': deque(maxlen=200),    # 眨眼时间戳
            'blink_frame_count':0,                    # 当前眨眼的连续帧数
            'mar_history':      deque(maxlen=150),    # ~15s MAR波形
            'yawn_timestamps':  deque(maxlen=30),     # 哈欠时间戳
            'last_ear':         0.30,                 # 上一帧EAR
            'last_pitch':       0.0,                  # 上一帧pitch
            'nod_events':       deque(maxlen=20),     # 点头事件
            'gaze_history':     deque(maxlen=300),    # 30s视线方向记录
            'action_history':   deque(maxlen=300),    # 30s动作状态记录
            'prev_learning_state': None,              # 上一帧学习状态
            'learning_state_since': None,             # 当前学习状态开始时间(UTC)
            'calib_yaw':        deque(maxlen=CALIBRATION_SAMPLES),
            'calib_pitch':      deque(maxlen=CALIBRATION_SAMPLES),
            'yaw_baseline':     0.0,
            'pitch_baseline':   0.0,
            'calibrated':       False,
            'sscma_score_history': deque(maxlen=30),
            'sscma_box_centers':   deque(maxlen=30),
            'sscma_restlessness':  0.0,
            'vad_speaking_count':   0,
            'vad_total_count':      0,
            'vad_speaking_pct':     0.0,
            'vad_last_report_time': None,
        }
    return _device_states[device_id]

# ============================================================
# 几何计算函数
# ============================================================

def _ear(pts: np.ndarray, idx: list) -> float:
    """眼部纵横比: (|p2-p6|+|p3-p5|) / (2*|p1-p4|)"""
    p = pts[idx]
    v1 = np.linalg.norm(p[1] - p[5])
    v2 = np.linalg.norm(p[2] - p[4])
    h  = np.linalg.norm(p[0] - p[3])
    return (v1 + v2) / (2.0 * h + 1e-6)


def _mar(pts: np.ndarray) -> float:
    """嘴部纵横比: |top-bottom| / |left-right|，哈欠时 > 0.55"""
    top    = pts[MOUTH_TOP]
    bottom = pts[MOUTH_BOTTOM]
    left   = pts[MOUTH_LEFT]
    right  = pts[MOUTH_RIGHT]
    v = np.linalg.norm(top - bottom)
    h = np.linalg.norm(left - right)
    return v / (h + 1e-6)


def _head_pose(face_landmarks, w, h):
    """几何法头部姿态 → (yaw, pitch, roll) 度

    只用鼻尖(1) + 左右眼外角(33, 263)三个最稳定的关键点，
    不依赖面部轮廓，帧间不会因轮廓点抖动而跳变。
    """
    lm = face_landmarks.landmark

    # 双眼信息
    left_eye = np.array([lm[33].x, lm[33].y])
    right_eye = np.array([lm[263].x, lm[263].y])
    eye_mid = (left_eye + right_eye) / 2
    eye_dist = max(np.linalg.norm(right_eye - left_eye), 1e-6)

    # 鼻尖
    nose = np.array([lm[1].x, lm[1].y])

    # yaw: 鼻尖水平偏移 / 眼距 → 映射为角度
    # 正视时鼻尖在双眼中间，偏移 = 0；侧脸时偏移 ≈ 0.5~1.0 倍眼距
    yaw = (nose[0] - eye_mid[0]) / eye_dist * 60.0

    # pitch: 鼻尖低于眼部的垂直距离 / 眼距
    # 中性位时鼻尖低于眼约 0.55 倍眼距，偏离此值 = 抬头/低头
    pitch_neutral = 0.55
    pitch = -((nose[1] - eye_mid[1]) / eye_dist - pitch_neutral) * 80.0

    # roll: 眼角连线
    dx = right_eye[0] - left_eye[0]
    dy = right_eye[1] - left_eye[1]
    roll = float(np.degrees(np.arctan2(dy, dx)))

    return round(yaw, 1), round(pitch, 1), round(roll, 1)


def _update_calibration(device_id: str, yaw: float, pitch: float):
    """自动标定头部姿态基线：收集前 N 帧，取中位数作为「自然看屏幕」姿态"""
    state = _get_state(device_id)
    if state['calibrated']:
        return
    state['calib_yaw'].append(yaw)
    state['calib_pitch'].append(pitch)
    if len(state['calib_yaw']) >= CALIBRATION_SAMPLES:
        yaws = sorted(state['calib_yaw'])
        pitches = sorted(state['calib_pitch'])
        state['yaw_baseline'] = yaws[len(yaws) // 2]
        state['pitch_baseline'] = pitches[len(pitches) // 2]
        state['calibrated'] = True
        print(f"[Analyzer] {device_id} 标定完成: yaw偏移={state['yaw_baseline']:.1f}°, pitch偏移={state['pitch_baseline']:.1f}°")


def _update_sscma_state(device_id: str, sscma_data: dict | None):
    """跟踪 SSCMA 检测数据：人员评分波动 + 边界框位移 → 躁动不安度 (Phase 2)"""
    if not sscma_data or not isinstance(sscma_data, dict):
        return
    state = _get_state(device_id)

    score = sscma_data.get('person_score', 0)
    if score > 0:
        state['sscma_score_history'].append(score)

    box = sscma_data.get('box', {})
    if box and box.get('w', 0) > 0:
        cx = box.get('x', 0) + box.get('w', 0) / 2
        cy = box.get('y', 0) + box.get('h', 0) / 2
        state['sscma_box_centers'].append((cx, cy))

    # 计算边界框抖动 → 躁动不安度 (std dev of box center positions)
    if len(state['sscma_box_centers']) >= 5:
        centers = list(state['sscma_box_centers'])
        cxs = [c[0] for c in centers]
        cys = [c[1] for c in centers]
        jitter = (float(np.std(cxs)) + float(np.std(cys))) / 2
        state['sscma_restlessness'] = round(min(jitter / 50.0, 1.0), 2)

# ============================================================
# 增强疲劳检测（多指标融合）
# ============================================================

def calc_fatigue(device_id: str, face_results, w: int, h: int,
                  sscma_restlessness: float = 0.0) -> dict:
    """疲劳检测 — 6项指标融合，含个人EAR基线自标定

    改进点：
    1. 前60帧自动标定个人EAR/MAR基线，基于偏离度而非绝对值
    2. 哈欠用频率而非平均MAR（张嘴大的人不会误判）
    3. 眨眼需连续2帧确认，过滤单帧噪声
    4. EMA平滑 + eyes-open衰减，疲劳不会瞬间清零
    """
    state = _get_state(device_id)
    now = datetime.now(timezone.utc)

    if not face_results or not face_results.multi_face_landmarks:
        # 无人脸时缓慢衰减
        if state['smoothed_fatigue'] > 0.01:
            state['smoothed_fatigue'] = max(0, state['smoothed_fatigue'] - 0.03)
        return {
            'fatigue_level': round(state['smoothed_fatigue'], 2),
            'fatigue_sub': {'ear': 0, 'perclos': 0, 'mar': 0, 'nod': 0, 'blink': 0},
        }

    lm = face_results.multi_face_landmarks[0]
    pts = np.array([(p.x * w, p.y * h) for p in lm.landmark])

    # ====== 个人基线标定 ======
    ear = (_ear(pts, LEFT_EYE) + _ear(pts, RIGHT_EYE)) / 2.0
    mar = _mar(pts)

    if state['ear_baseline'] is None:
        state['ear_calib_samples'].append(ear)
    if state['mar_baseline'] is None:
        state['mar_history'].append(mar)

    if state['ear_baseline'] is None and len(state['ear_calib_samples']) >= EAR_CALIB_FRAMES:
        samples = sorted(state['ear_calib_samples'])
        # 取上四分位数作为睁眼基线（过滤半闭眼帧）
        state['ear_baseline'] = samples[int(len(samples) * 0.75)]
        state['mar_baseline'] = np.mean(list(state['mar_history'])) if state['mar_history'] else 0.35
        print(f"[FatigueCalib] {device_id}: EAR基线={state['ear_baseline']:.3f}, MAR基线={state['mar_baseline']:.3f}")

    # 使用个人基线，未标定时用默认值
    ear_bl = state['ear_baseline'] if state['ear_baseline'] else 0.30
    mar_bl = state['mar_baseline'] if state['mar_baseline'] else 0.35

    # ====== 1. EAR — 基于个人基线的偏离度 ======
    if ear_bl > 0:
        ear_deviation = max(0, (ear_bl - ear) / (ear_bl * (1.0 - EAR_FULLY_CLOSED)))
    else:
        ear_deviation = 0.0
    # ear_deviation: 0=正常, 1=完全闭合

    # 闭眼持续时间
    if ear < ear_bl * EAR_CLOSURE_RATIO:
        if state['closed_since'] is None:
            state['closed_since'] = now
        state['closed_duration'] = (now - state['closed_since']).total_seconds()
    else:
        state['closed_since'] = None
        state['closed_duration'] = 0.0

    close_score = min(1.0, state['closed_duration'] / 3.0)      # 闭眼3s=严重
    ear_total = 0.55 * close_score + 0.45 * ear_deviation

    # ====== 2. PERCLOS — 基于个人基线的闭眼占比 ======
    is_closed = ear < ear_bl * EAR_CLOSURE_RATIO
    state['perclos_window'].append((now, is_closed))

    cutoff = now.timestamp() - PERCLOS_WINDOW_S
    while state['perclos_window'] and state['perclos_window'][0][0].timestamp() < cutoff:
        state['perclos_window'].popleft()

    if state['perclos_window']:
        closed_count = sum(1 for _, c in state['perclos_window'] if c)
        perclos = closed_count / len(state['perclos_window'])
    else:
        perclos = 0.0
    perclos_score = min(1.0, perclos / 0.30)

    # ====== 3. MAR 哈欠 ======
    yawn_threshold = max(MAR_YAWN_ABS, mar_bl * MAR_YAWN_RATIO)
    if mar > yawn_threshold:
        # 5秒内不重复计数，避免一次哈欠多次触发
        last = state['yawn_timestamps'][-1] if state['yawn_timestamps'] else None
        if last is None or (now - last).total_seconds() > 5:
            state['yawn_timestamps'].append(now)

    # 清理 >60s 的旧记录
    cutoff_yawn = now.timestamp() - 60.0
    while state['yawn_timestamps'] and state['yawn_timestamps'][0].timestamp() < cutoff_yawn:
        state['yawn_timestamps'].popleft()

    yawns_per_min = len(state['yawn_timestamps'])
    mar_score = min(1.0, yawns_per_min / 4.0)  # 每分钟4次哈欠=严重疲劳

    # ====== 4. 头部点头 ======
    pitch = _head_pose(face_results.multi_face_landmarks[0], w, h)[1]
    state['pitch_history'].append((now, pitch))

    cutoff_nod = now.timestamp() - 4.0
    while state['pitch_history'] and state['pitch_history'][0][0].timestamp() < cutoff_nod:
        state['pitch_history'].popleft()

    nod_score = 0.0
    if len(state['pitch_history']) >= 5:
        pitches = [(t, p) for t, p in state['pitch_history']]
        pitch_values = [p for _, p in pitches]
        pitch_range = max(pitch_values) - min(pitch_values)
        min_idx = pitch_values.index(min(pitch_values))
        max_idx = pitch_values.index(max(pitch_values))
        time_span = abs((pitches[max_idx][0] - pitches[min_idx][0]).total_seconds())

        if pitch_range > NOD_PITCH_DROP and time_span < NOD_RECOVERY_S:
            recent_pitches = list(state['pitch_history'])[-5:]
            if recent_pitches[-1][1] > recent_pitches[0][1]:
                state['nod_events'].append(now)
                nod_score = min(1.0, pitch_range / 20.0)

    recent_nods = sum(1 for t in state['nod_events'] if (now - t).total_seconds() < 60)
    nod_total = min(1.0, nod_score * 0.7 + recent_nods / 5.0 * 0.3)

    # ====== 5. 眨眼频率（需连续2帧确认，过滤单帧噪声）======
    prev_ear = state['last_ear']
    state['last_ear'] = ear

    blink_threshold = ear_bl * 0.65  # 低于基线65%=眨眼
    if prev_ear > blink_threshold and ear < blink_threshold:
        state['blink_frame_count'] += 1
    elif ear < blink_threshold:
        state['blink_frame_count'] += 1  # 持续闭眼
    else:
        # EAR恢复 — 之前的闭眼是否构成一次眨眼
        if state['blink_frame_count'] >= 2:
            state['blink_timestamps'].append(now)
        state['blink_frame_count'] = 0

    cutoff_blink = now.timestamp() - 60.0
    while state['blink_timestamps'] and state['blink_timestamps'][0].timestamp() < cutoff_blink:
        state['blink_timestamps'].popleft()

    blink_rate = len(state['blink_timestamps'])
    if 14 <= blink_rate <= 24:
        blink_score = 0.0
    elif blink_rate > 24:
        blink_score = min(1.0, (blink_rate - 24) / 16.0)
    else:  # <14
        blink_score = min(1.0, (14 - blink_rate) / 10.0)

    # ====== 融合 ======
    raw_fatigue = (
        0.25 * ear_total +
        0.30 * perclos_score +
        0.20 * mar_score +
        0.15 * nod_total +
        0.10 * blink_score
    )

    # SSCMA 身体躁动：只提升已有疲劳
    if sscma_restlessness > 0.5 and raw_fatigue > 0.25:
        raw_fatigue += (sscma_restlessness - 0.5) * 0.12

    raw_fatigue = min(max(raw_fatigue, 0), 1.0)

    # EMA 平滑：疲劳不会突变
    alpha = FATIGUE_EMA_ALPHA
    prev_smooth = state['smoothed_fatigue']
    smoothed = alpha * raw_fatigue + (1.0 - alpha) * prev_smooth

    # Eyes-open 衰减：当眼睛睁开且疲劳信号低时，缓慢降低
    if raw_fatigue < 0.15 and state['closed_duration'] == 0:
        smoothed = max(0, smoothed - FATIGUE_DECAY_RATE)

    smoothed = round(min(max(smoothed, 0), 1), 2)
    state['smoothed_fatigue'] = smoothed

    return {
        'fatigue_level': smoothed,
        'fatigue_sub': {
            'ear':      round(ear_total, 2),
            'perclos':  round(perclos_score, 2),
            'mar':      round(mar_score, 2),
            'nod':      round(nod_total, 2),
            'blink':    round(blink_score, 2),
        },
    }

# ============================================================
# 分心检测
# ============================================================

def calc_distraction(device_id: str, face_results, w: int, h: int,
                     action_state: str = "", gaze_direction: str = "") -> float:
    """分心度：几何头部姿态 + 动作/注视上下文的综合分值

    几何基线来自头部偏离角度，上下文调节基于已检测的行为状态。
    """
    if not face_results or not face_results.multi_face_landmarks:
        # 无人脸但有 SSCMA 检测到身体时 → 可能正在玩手机/趴下
        if action_state == "playing_phone":
            return 0.75
        if action_state == "lying_down":
            return 0.55
        return 0.0

    yaw, pitch, _ = _head_pose(face_results.multi_face_landmarks[0], w, h)

    # 看向摄像头本身 → 几何分心度为 0
    looking_at_camera = abs(yaw) < 22 and abs(pitch) < 22
    if looking_at_camera:
        geo_score = 0.0
    else:
        state = _get_state(device_id)
        yaw -= state['yaw_baseline']
        pitch -= state['pitch_baseline']
        dev = np.sqrt(yaw**2 + pitch**2)
        geo_score = round(min(max((dev - 15) / 30, 0), 1), 2)

    # ---- 上下文调节：基于动作状态 + 注视方向 ----
    if action_state == "turning_around":
        # 转身 = 明确分心，不受头部朝向限制
        return max(geo_score + 0.40, 0.75)
    if action_state == "playing_phone":
        return max(geo_score + 0.35, 0.70)
    if action_state == "lying_down":
        return max(geo_score, 0.50)
    if action_state == "idle" and gaze_direction == "away":
        return max(geo_score, 0.45)
    # CBPH-Net 检测的学习状态：正向行为，降低几何分心分
    if action_state == "writing" and gaze_direction == "down":
        return min(geo_score, 0.20)
    if action_state == "reading" and gaze_direction in ("down", "screen"):
        return min(geo_score, 0.25)
    if action_state == "listening" and gaze_direction == "screen":
        return min(geo_score, 0.15)

    return geo_score


def calc_gaze_direction(device_id: str, face_results, w: int, h: int) -> str:
    """注视方向（自动标定基线后判断）

    几何法头部姿态，不依赖相机内参。
    看向摄像头本身始终视为"screen"——小智放侧面时看小智是正常交互。
    """
    if not face_results or not face_results.multi_face_landmarks:
        return "away"
    yaw, pitch, _ = _head_pose(face_results.multi_face_landmarks[0], w, h)
    _update_calibration(device_id, yaw, pitch)
    state = _get_state(device_id)

    # 诊断日志：前5帧每次打印，之后每50帧一次
    hist_len = len(state['calib_yaw'])
    logged_attr = f'_logged_{device_id}'
    if hist_len <= 5 or (hist_len % 50 == 0 and not getattr(calc_gaze_direction, logged_attr, False)):
        if hist_len > 5:
            setattr(calc_gaze_direction, logged_attr, True)
        print(f"[GazeDiag] {device_id}: raw(yaw={yaw:.1f}, pitch={pitch:.1f}) "
              f"baseline(yaw={state['yaw_baseline']:.1f}, pitch={state['pitch_baseline']:.1f}) "
              f"calibrated(yaw={yaw - state['yaw_baseline']:.1f}, pitch={pitch - state['pitch_baseline']:.1f}) "
              f"calibrated={state['calibrated']}")

    # 看向摄像头本身 → 始终 "screen"
    if abs(yaw) < 22 and abs(pitch) < 22:
        return "screen"

    yaw -= state['yaw_baseline']
    pitch -= state['pitch_baseline']
    if abs(yaw) > 40: return "away"
    if pitch < -25: return "down"
    if pitch > 25: return "up"
    return "screen"

# ============================================================
# 动作状态检测
# ============================================================

def calc_action_state(pose_results, cbph_action: str | None = None,
                      cbph_conf: float = 0.0):
    """
    动作状态检测 — CBPH-Net 优先，Pose 规则回退

    CBPH-Net 置信度 ≥ 0.4 时直接使用其结果；
    低置信度或无检测时回退 MediaPipe Pose 几何规则（趴桌/玩手机/idle）。

    返回 (state, torso_angle)
    """
    # CBPH-Net 优先：置信度够高直接使用
    if cbph_action and cbph_conf >= 0.4:
        return cbph_action, 90.0

    # 回退：原有 MediaPipe Pose 规则
    return _legacy_action_state(pose_results)


def _legacy_action_state(pose_results):
    """
    原有 MediaPipe Pose 几何规则 — 保留用于：
    - lying_down（趴桌休息，CBPH-Net 无此类别）
    - playing_phone（玩手机，CBPH-Net 无此类别）
    - idle（无动作时的兜底）
    """
    if not pose_results or not pose_results.pose_landmarks:
        return "idle", 90.0

    lm = pose_results.pose_landmarks.landmark
    nose   = np.array([lm[0].x, lm[0].y])
    l_w    = np.array([lm[15].x, lm[15].y])
    r_w    = np.array([lm[16].x, lm[16].y])
    l_s    = np.array([lm[11].x, lm[11].y])
    r_s    = np.array([lm[12].x, lm[12].y])
    l_h    = np.array([lm[23].x, lm[23].y])
    r_h    = np.array([lm[24].x, lm[24].y])

    mid_s = (l_s + r_s) / 2
    mid_h = (l_h + r_h) / 2
    wrist_y = (l_w[1] + r_w[1]) / 2

    torso_vec = mid_h - mid_s
    torso_angle = np.degrees(np.arctan2(torso_vec[1], abs(torso_vec[0]) + 1e-6))

    if torso_angle < 25:
        return "lying_down", torso_angle

    # 玩手机核心特征：至少一只手腕靠近脸部（手机在脸附近）
    # 用欧氏距离避免轴对齐阈值过严——手腕在鼻子斜下方也计入
    def _wrist_dist_to_nose(w):
        return np.linalg.norm(w - nose)
    any_wrist_near_face = _wrist_dist_to_nose(l_w) < 0.18 or _wrist_dist_to_nose(r_w) < 0.18

    # 条件1: 双手模式——双手靠近 + 手腕高于肩 + 任一手靠近脸
    hands_raised = wrist_y < mid_s[1] + 0.04
    hands_close = abs(l_w[0] - r_w[0]) < 0.18
    if hands_raised and hands_close and any_wrist_near_face:
        return "playing_phone", torso_angle

    # 条件2: 单手模式——手高差大 + 高的一手靠近脸
    hand_diff = abs(l_w[1] - r_w[1])
    if hand_diff > 0.06 and any_wrist_near_face:
        return "playing_phone", torso_angle

    # 条件3: 单手举高 + 另一手很低（Pose漏检补偿）+ 高的一手靠近脸
    one_hand_high = (l_w[1] < mid_s[1]) or (r_w[1] < mid_s[1])
    other_hand_low = (l_w[1] > mid_h[1]) or (r_w[1] > mid_h[1])
    if one_hand_high and other_hand_low and any_wrist_near_face:
        return "playing_phone", torso_angle

    if nose[1] > mid_s[1] + 0.08:
        return "reading", torso_angle
    if wrist_y > mid_s[1]:
        return "writing", torso_angle
    return "idle", torso_angle

# ============================================================
# 学习状态分类器
# ============================================================

def calc_learning_state(device_id: str, action: str, gaze: str, fatigue: float) -> str:
    """
    多维度学习状态分类（CBPH-Net + MediaPipe 融合）：

    | 状态              | 动作来源          | 视线   | 疲劳 | 说明              |
    |-------------------|------------------|--------|------|-------------------|
    | engaged_screen    | CBPH listening   | screen | 低   | 听课看屏幕         |
    | engaged_writing   | CBPH writing     | down   | 低   | 做题写字           |
    | engaged_reading   | CBPH reading     | down   | 低   | 低头看书           |
    | thinking          | CBPH 无检测/idle | 不定   | 低   | 短暂思考/兜底      |
    | distracted_phone  | Pose 规则        | 任意   | 任意  | 玩手机=分心        |
    | distracted_away   | CBPH turning_around 或 idle+away≥30s | 低 | 走神/转身 |
    | fatigued          | MediaPipe         | 任意   | ≥0.6 | 疲劳需要休息       |
    | resting           | Pose 规则        | 任意   | 任意  | 趴桌休息           |
    | absent            | MediaPipe        | —      | —    | 画面无人           |

    优先级：absent > resting > fatigued > distracted_phone > distracted_away > engaged_* > thinking
    """
    state = _get_state(device_id)
    now = datetime.now(timezone.utc)

    # 记录当前帧的视线和动作
    state['gaze_history'].append((now, gaze))
    state['action_history'].append((now, action))

    # 清理 >60s 的历史
    cutoff = now.timestamp() - 60.0
    for hist in [state['gaze_history'], state['action_history']]:
        while hist and hist[0][0].timestamp() < cutoff:
            hist.popleft()

    # 计算当前视线已持续多久
    same_gaze_start = now
    for t, g in reversed(state['gaze_history']):
        if g != gaze:
            break
        same_gaze_start = t
    gaze_duration = (now - same_gaze_start).total_seconds()

    # 计算当前动作已持续多久
    same_action_start = now
    for t, a in reversed(state['action_history']):
        if a != action:
            break
        same_action_start = t
    action_duration = (now - same_action_start).total_seconds()

    # ---- 按优先级判定 ----

    # 1. 玩手机 = 分心（无论其他信号）
    if action == "playing_phone":
        new_state = "distracted_phone"

    # 2. 趴桌 = 休息
    elif action == "lying_down":
        new_state = "resting"

    # 3. 疲劳（阈值0.6，无论当前在做什么）
    elif fatigue >= 0.6:
        new_state = "fatigued"

    # 4. CBPH 转身 = 直接分心（无需时长判断）
    elif action == "turning_around":
        new_state = "distracted_away"

    # 5. 长时间看别处 = 分心（Pose idle 时的回退判断）
    elif action == "idle" and gaze == "away" and gaze_duration >= THINKING_MAX_S:
        new_state = "distracted_away"

    # 6. CBPH 写字 = 学习（做题）
    elif action == "writing":
        new_state = "engaged_writing"

    # 7. CBPH 阅读 = 学习（读书）
    elif action == "reading":
        new_state = "engaged_reading"

    # 8. CBPH 听讲 或 看屏幕 = 学习（听课）
    elif action == "listening" or (gaze == "screen" and action in ("idle", "reading")):
        new_state = "engaged_screen"

    # 9. 短暂看别处 = 思考（Pose idle + 注视不定）
    elif action == "idle" and gaze in ("away", "up") and gaze_duration < THINKING_MAX_S:
        new_state = "thinking"

    # 10. 默认：思考中（不确定时偏向正向）
    else:
        new_state = "thinking"

    # 状态切换防抖：新状态至少持续2秒才切换
    if new_state != state['prev_learning_state']:
        if state['learning_state_since'] is None:
            state['learning_state_since'] = now
        elif (now - state['learning_state_since']).total_seconds() >= 2.0:
            state['prev_learning_state'] = new_state
            state['learning_state_since'] = now
        # 不足2秒，保持旧状态
        new_state = state['prev_learning_state']
    else:
        state['learning_state_since'] = now

    return new_state

# ============================================================
# 单帧综合分析
# ============================================================

def analyze_frame(device_id: str, frame: np.ndarray,
                  sscma_data: dict | None = None, vad_data: dict | None = None) -> dict:
    """
    综合分析一帧——CBPH-Net 动作检测 + MediaPipe 生理状态分析

    CBPH-Net (YOLOv8n ONNX) 负责动作分类，高置信度时跳过 Pose 以节省时间。
    MediaPipe FaceMesh 始终运行（疲劳+注视+分心需要）。

    sscma_data: SSCMA AI co-processor detection results from ESP32.
    vad_data:   VAD voice activity detection from ESP32.
    """
    if frame.shape[:2] != (240, 320):
        frame = cv2.resize(frame, (320, 240))
    h, w = frame.shape[:2]

    # ---- CBPH-Net 动作检测 (Phase 4) ----
    cbph_action = None
    cbph_conf = 0.0
    if cbph_ready():
        try:
            cbph_action, cbph_conf = cbph_infer(frame)
        except Exception as e:
            print(f"[Analyzer] CBPH-Net 推理失败: {e}")

    # ---- 运行 MediaPipe ----
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    face_results = face_mesh.process(rgb)

    # Pose 按需运行：CBPH 高置信度时跳过，节省 ~15ms
    if cbph_conf >= 0.5:
        pose_results = None
    else:
        pose_results = pose_model.process(rgb)

    # ---- 基础检测 ----
    face_ok = face_results.multi_face_landmarks is not None
    pose_ok = pose_results is not None and pose_results.pose_landmarks is not None
    person_present = face_ok or pose_ok

    # ---- SSCMA 辅助：人员存在性交叉验证 (Phase 1) ----
    sscma_person_score = 0
    if sscma_data and isinstance(sscma_data, dict):
        sscma_person_score = sscma_data.get("person_score", 0)

    # ---- SSCMA 辅助：跟踪人员评分/框位移 → 躁动不安度 (Phase 2) ----
    _update_sscma_state(device_id, sscma_data)

    # ---- VAD 辅助：跟踪说话占比 (Phase 3) ----
    sscma_restlessness = 0.0
    vad_speaking_pct = 0.0
    if vad_data and isinstance(vad_data, dict):
        state = _get_state(device_id)
        state['vad_total_count'] += 1
        if vad_data.get("speaking"):
            state['vad_speaking_count'] += 1
        if state['vad_total_count'] > 0:
            state['vad_speaking_pct'] = round(
                state['vad_speaking_count'] / state['vad_total_count'], 2)
        vad_speaking_pct = state['vad_speaking_pct']
        sscma_restlessness = state.get('sscma_restlessness', 0.0)

    # ---- 动作状态：CBPH-Net 优先 ----
    action_state, torso_angle = calc_action_state(
        pose_results, cbph_action, cbph_conf)

    gaze = calc_gaze_direction(device_id, face_results, w, h)
    distraction = calc_distraction(device_id, face_results, w, h,
                                     action_state, gaze)

    # ---- 增强疲劳检测 (含 SSCMA 躁动不安信号) ----
    fatigue_result = calc_fatigue(device_id, face_results, w, h,
                                  sscma_restlessness=sscma_restlessness)
    fatigue_level = fatigue_result['fatigue_level']

    # ---- 疲劳时分心度不应为0：疲劳=实际学习效率低，即使头朝屏幕 ----
    if fatigue_level > 0.4:
        distraction = max(distraction, round((fatigue_level - 0.4) * 0.4, 2))

    # ---- 学习状态分类 ----
    if not person_present:
        learning_state = "absent"
        # 人离开时重置状态跟踪，回来时从头开始判断
        state = _get_state(device_id)
        state['prev_learning_state'] = "absent"
        state['learning_state_since'] = None
    else:
        learning_state = calc_learning_state(device_id, action_state, gaze, fatigue_level)

    return {
        "fatigue_level":     fatigue_level,
        "fatigue_sub":       fatigue_result['fatigue_sub'],
        "distraction_level": distraction,
        "gaze_direction":    gaze,
        "action_state":      action_state,
        "torso_angle":       torso_angle,
        "learning_state":    learning_state,
        "difficulty_indicator": 0.0,
        "person_present":    person_present,
        "sscma_person_score": sscma_person_score,
        "sscma_restlessness": sscma_restlessness,
        "vad_speaking_pct":  vad_speaking_pct,
    }

# ============================================================
# 后台分析协程
# ============================================================

def _build_status_message(result: dict) -> dict:
    """将学习状态映射为设备端的表情+文字+语音提醒"""
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


async def run_analyzer(frame_queue: asyncio.Queue, output_queue: asyncio.Queue = None):
    trackers = {}
    last_cleanup = 0
    print("[Analyzer] 分析器已启动（增强疲劳+学习状态分类）")

    # 启动时运行一次清理
    await asyncio.to_thread(_cleanup_old_records)

    while True:
        try:
            p = await asyncio.wait_for(frame_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            # 每小时清理一次过期数据
            now_ts = datetime.now(timezone.utc).timestamp()
            if now_ts - last_cleanup > 3600:
                await asyncio.to_thread(_cleanup_old_records)
                last_cleanup = now_ts
            continue

        try:
            # 每小时清理一次过期数据
            now_ts = datetime.now(timezone.utc).timestamp()
            if now_ts - last_cleanup > 3600:
                await asyncio.to_thread(_cleanup_old_records)
                last_cleanup = now_ts

            device_id = p["device_id"]
            sscma_data = p.get("sscma")
            vad_data = p.get("vad")
            result = analyze_frame(device_id, p["image"], sscma_data, vad_data)

            from difficulty import DifficultyTracker
            if device_id not in trackers:
                trackers[device_id] = DifficultyTracker()

            # 无人帧不计入困难度历史，避免污染60s滑动窗口
            if result.get("person_present"):
                trackers[device_id].add_result(result)
                result["difficulty_indicator"] = trackers[device_id].compute()
            # else: 保持上一帧的 difficulty_indicator（默认为0.0，来自 analyze_frame）

            await asyncio.to_thread(_write_db, device_id, result, p["filepath"])

            # 推入 Agent 行为缓冲（供 LLM 分析使用）
            if result.get("person_present"):
                try:
                    push_behavior(result)
                except Exception:
                    pass

            # 推送分析结果到设备（用于屏幕交互）
            if output_queue is not None:
                status_msg = _build_status_message(result)
                status_msg["device_id"] = device_id
                try:
                    output_queue.put_nowait(status_msg)
                except asyncio.QueueFull:
                    pass
        except Exception as e:
            print(f"[Analyzer] 分析帧失败: {e}")
        finally:
            frame_queue.task_done()


# ============================================================
# 每设备缺席状态（用于自动切分学习时段）
# ============================================================

_absence_state = {}  # device_id -> {'absence_start': datetime, 'session_ended': bool}


def _write_db(device_id, result, filepath):
    from config import SESSION_MAX_MINUTES, ABSENCE_GRACE_S, SAVE_ALL_FRAMES
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc)
        person_present = result.get("person_present", True)

        with conn.cursor() as cur:
            # ---- 查询当前活跃 session ----
            cur.execute(
                "SELECT id, start_time FROM sessions WHERE device_id=%s AND status='active'",
                (device_id,)
            )
            row = cur.fetchone()

            # ---- 缺席状态管理 ----
            # SSCMA辅助：若 MediaPipe 未检测到人但 SSCMA 检测到，延长宽限期
            sscma_person_score = result.get("sscma_person_score", 0)
            effective_grace = ABSENCE_GRACE_S
            if not person_present and sscma_person_score > 85:
                effective_grace = ABSENCE_GRACE_S * 2  # 30s when SSCMA still sees person

            if not person_present:
                if device_id not in _absence_state:
                    _absence_state[device_id] = {'absence_start': now, 'session_ended': False}
                absence_info = _absence_state[device_id]

                if not absence_info['session_ended']:
                    absence_sec = (now - absence_info['absence_start']).total_seconds()
                    if absence_sec > effective_grace:
                        # 超过宽限期：关闭当前 session
                        if row is not None:
                            cur.execute(
                                "UPDATE sessions SET status='ended', end_time=%s WHERE id=%s",
                                (absence_info['absence_start'], row["id"])
                            )
                            conn.commit()
                        absence_info['session_ended'] = True

                # 当前 session 已因缺席关闭，无人帧不再写入
                if absence_info['session_ended']:
                    return
            else:
                # 人回来了，清除缺席状态
                if device_id in _absence_state:
                    del _absence_state[device_id]

            # ---- 获取或创建活跃 session ----
            if row is None:
                cur.execute("INSERT INTO sessions (device_id,status) VALUES (%s,'active')", (device_id,))
                conn.commit()
                sid = cur.lastrowid
            else:
                sid = row["id"]
                start = row["start_time"]
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                if (now - start).total_seconds() > SESSION_MAX_MINUTES * 60:
                    cur.execute(
                        "UPDATE sessions SET status='ended', end_time=%s WHERE id=%s",
                        (now, sid)
                    )
                    cur.execute("INSERT INTO sessions (device_id,status) VALUES (%s,'active')", (device_id,))
                    conn.commit()
                    sid = cur.lastrowid

            # ---- 隐私：非告警帧不存图 ----
            alert_states = {"distracted_phone", "distracted_away", "fatigued", "resting"}
            is_alert = (
                result["fatigue_level"] > 0.5 or
                result["distraction_level"] > 0.5 or
                result["difficulty_indicator"] > 0.5 or
                result.get("learning_state", "") in alert_states
            )
            stored_path = filepath
            if not SAVE_ALL_FRAMES and not is_alert and filepath:
                try:
                    os.remove(filepath)
                except OSError:
                    pass
                stored_path = ""

            # ---- 写入分析结果 ----
            cur.execute(
                """INSERT INTO analysis_results
                (session_id,timestamp,fatigue_level,distraction_level,
                 gaze_direction,action_state,learning_state,difficulty_indicator,raw_frame_path,person_present)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (sid, now,
                 result["fatigue_level"], result["distraction_level"],
                 result["gaze_direction"], result["action_state"],
                 result.get("learning_state", ""),
                 result["difficulty_indicator"], stored_path,
                 int(person_present)))
            conn.commit()
    finally:
        conn.close()


def _cleanup_old_records():
    """清理超过保留期的帧图片和数据库记录"""
    from config import FRAME_SAVE_DIR, FRAME_RETENTION_DAYS
    import time
    cutoff = time.time() - FRAME_RETENTION_DAYS * 86400
    deleted_files = 0
    deleted_rows = 0

    # 1. 清理帧文件目录中的旧文件
    if os.path.isdir(FRAME_SAVE_DIR):
        for root, dirs, files in os.walk(FRAME_SAVE_DIR, topdown=False):
            for name in files:
                fpath = os.path.join(root, name)
                try:
                    if os.path.getmtime(fpath) < cutoff:
                        os.remove(fpath)
                        deleted_files += 1
                except OSError:
                    pass
            # 删除空目录
            for name in dirs:
                dpath = os.path.join(root, name)
                try:
                    os.rmdir(dpath)
                except OSError:
                    pass

    # 2. 清理数据库中旧记录的 raw_frame_path（文件已删除，避免前端显示无效路径）
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
            cur.execute(
                "UPDATE analysis_results SET raw_frame_path='' WHERE timestamp < %s AND raw_frame_path != ''",
                (cutoff_dt,)
            )
            deleted_rows = cur.rowcount
            conn.commit()
    finally:
        conn.close()

    if deleted_files or deleted_rows:
        print(f"[Cleanup] 清理完成: 删除 {deleted_files} 个旧文件, 更新 {deleted_rows} 条数据库记录")
