"""困难度计算：基于60秒历史的多维度加权融合

维度：
1. struggle_ratio  (0.25) — 挣扎状态占比（distracted/fatigued/resting）
2. volatility      (0.20) — 学习状态频繁切换度
3. fatigue_drift   (0.18) — 平均疲劳水平
4. blank_stare     (0.13) — 空白凝视：idle+screen 且无书写/阅读交互
5. posture_decline (0.09) — 姿态随时间坍塌的趋势
6. restlessness    (0.08) — SSCMA 身体躁动不安（框中心抖动频率，Phase 2）
7. vad_speaking    (0.07) — VAD 说话时间占比（Phase 3）
"""
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import numpy as np


# 挣扎状态：明确表示学生无法正常学习
STRUGGLE_STATES = {"distracted_phone", "distracted_away", "fatigued", "resting"}

# 投入状态：明确表示在有效学习
ENGAGED_STATES = {"engaged_screen", "engaged_writing", "engaged_reading"}


@dataclass
class DifficultyTracker:
    history: deque = field(default_factory=lambda: deque(maxlen=120))
    window_seconds: float = 60.0

    def add_result(self, result: dict):
        self.history.append({
            "ts": datetime.now(timezone.utc),
            "learning_state": result.get("learning_state", ""),
            "action_state": result.get("action_state", ""),
            "gaze_direction": result.get("gaze_direction", ""),
            "fatigue_level": result.get("fatigue_level", 0.0),
            "torso_angle": result.get("torso_angle", 90.0),
            "sscma_restlessness": result.get("sscma_restlessness", 0.0),
            "vad_speaking_pct": result.get("vad_speaking_pct", 0.0),
        })

    def compute(self) -> float:
        if len(self.history) < 5:
            return 0.0

        now = datetime.now(timezone.utc)
        recent = [r for r in self.history
                  if (now - r["ts"]).total_seconds() <= self.window_seconds]
        if len(recent) < 5:
            return 0.0

        n = len(recent)

        # ================================================
        # 维度1: struggle_ratio — 挣扎状态占比 (0.30)
        # ================================================
        struggle_count = sum(1 for r in recent
                            if r["learning_state"] in STRUGGLE_STATES)
        struggle_ratio = struggle_count / n

        # ================================================
        # 维度2: volatility — 学习状态切换频率 (0.25)
        # 频繁在 engaged ↔ thinking ↔ distracted 之间跳 = 无法专注 = 困难
        # ================================================
        transitions = 0
        for i in range(1, n):
            if recent[i]["learning_state"] != recent[i - 1]["learning_state"]:
                transitions += 1
        # 最大可能切换次数 = n-1，归一化
        volatility = transitions / max(n - 1, 1)

        # ================================================
        # 维度3: fatigue_drift — 平均疲劳水平 (0.20)
        # ================================================
        fatigue_values = [r["fatigue_level"] for r in recent]
        fatigue_drift = np.mean(fatigue_values)

        # ================================================
        # 维度4: blank_stare — 空洞凝视 (0.15)
        # 连续 idle + screen 且窗口内没有 writing/reading 交互
        # ================================================
        idle_screen_pairs = 0
        for i in range(1, n):
            prev = recent[i - 1]
            curr = recent[i]
            if (prev["action_state"] == "idle" and prev["gaze_direction"] == "screen" and
                curr["action_state"] == "idle" and curr["gaze_direction"] == "screen"):
                idle_screen_pairs += 1

        # 如果窗口内有 writing 或 reading，说明在交替学习，不算 blank_stare
        has_interaction = any(
            r["action_state"] in ("writing", "reading")
            for r in recent
        )
        if has_interaction:
            blank_stare = 0.0
        else:
            blank_stare = idle_screen_pairs / max(n - 1, 1)

        # ================================================
        # 维度5: posture_decline — 姿态坍塌趋势 (0.10)
        # 躯干角度随时间递减 = 逐渐趴下 = 困难
        # ================================================
        if n >= 10:
            timestamps = np.array([(r["ts"] - recent[0]["ts"]).total_seconds()
                                   for r in recent])
            angles = np.array([r["torso_angle"] for r in recent])
            # 线性回归斜率：负斜率 = 角度在减小（趴下去）
            if np.std(timestamps) > 1e-6:
                slope = np.polyfit(timestamps, angles, 1)[0]
                # 斜率 −5°/s → posture_decline = 1.0; 0 或正 → 0
                posture_decline = max(0.0, min(-slope / 5.0, 1.0))
            else:
                posture_decline = 0.0
        else:
            posture_decline = 0.0

        # ================================================
        # 维度6: restlessness — SSCMA 身体躁动不安 (0.08)
        # 长期学习后的躁动不安是困难学习的伴随信号
        # ================================================
        restlessness = np.mean([r.get("sscma_restlessness", 0.0) for r in recent])

        # ================================================
        # 维度7: vad_speaking — 说话时间占比 (0.07)
        # 学习中频繁说话(非交互模式)可能是分心/困难信号
        # ================================================
        vad_values = [r.get("vad_speaking_pct", 0.0) for r in recent]
        avg_vad = np.mean(vad_values) if vad_values else 0.0

        # ================================================
        # 加权融合
        # ================================================
        difficulty = (
            0.25 * struggle_ratio +
            0.20 * volatility +
            0.18 * fatigue_drift +
            0.13 * blank_stare +
            0.09 * posture_decline +
            0.08 * restlessness +
            0.07 * avg_vad
        )
        return round(min(max(difficulty, 0.0), 1.0), 2)
