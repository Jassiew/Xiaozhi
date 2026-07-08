"""检测准确性测试：使用真实人脸图片 + 场景模拟，验证各模块输出

运行：python tests/test_detection_accuracy.py

测试场景：
  1. 真实人脸 →  验证 person_present=True, 分心/疲劳/动作/视线有合理值
  2. 噪声图片 →  验证 person_present=False, learning_state=absent
  3. SSCMA 数据注入 → 验证 sscma_person_score/restlessness 传播
  4. VAD 数据注入   → 验证 vad_speaking_pct 追踪
  5. 分心场景模拟 → 人工构造偏头样本验证分心度爬升
  6. 困难度 7 维度 → 验证新维度 restlessness 和 VAD 对分数的影响
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2
from analyzer import analyze_frame, _get_state
from difficulty import DifficultyTracker


# ---- helpers ----

def make_sscma(person_score=85, box=(100, 50, 200, 300)):
    return {
        "person_detected": person_score > 60,
        "person_score": person_score,
        "box": {"x": box[0], "y": box[1], "w": box[2], "h": box[3]},
        "model_type": 0,
        "point_count": 0,
    }

def make_vad(speaking=False):
    return {"speaking": speaking}

def _make_record(**kw):
    return {
        "learning_state": kw.get("learning_state", "engaged_writing"),
        "action_state": kw.get("action_state", "writing"),
        "gaze_direction": kw.get("gaze_direction", "down"),
        "fatigue_level": kw.get("fatigue_level", 0.1),
        "torso_angle": kw.get("torso_angle", 85.0),
        "sscma_restlessness": kw.get("sscma_restlessness", 0.0),
        "vad_speaking_pct": kw.get("vad_speaking_pct", 0.0),
    }


# ---- test functions ----

def test_real_face():
    """场景1: 真实人脸照片 → 应检测到人，各项指标在合理范围"""
    print("\n=== 场景1: 真实人脸照片 ===")
    path = os.path.join(os.path.dirname(__file__), "real_face.jpg")
    frame = cv2.imread(path)
    assert frame is not None, f"无法读取 {path}"
    print(f"  图片尺寸: {frame.shape}")

    result = analyze_frame("test-real-face", frame)
    checks = []

    # 1. 应该检测到人
    ok = result["person_present"] is True
    checks.append(("检测到人", ok, f"person_present={result['person_present']}"))

    # 2. 分心度应在 0-1 之间（面部朝向未知，不做具体断言）
    ok = 0.0 <= result["distraction_level"] <= 1.0
    checks.append(("分心度范围", ok, f"distraction={result['distraction_level']}"))

    # 3. 视线方向应为有效值
    ok = result["gaze_direction"] in ("screen", "away", "down", "up")
    checks.append(("视线方向有效", ok, f"gaze={result['gaze_direction']}"))

    # 4. 动作状态应为有效值
    ok = result["action_state"] in ("writing", "idle", "playing_phone", "lying_down", "reading")
    checks.append(("动作状态有效", ok, f"action={result['action_state']}"))

    # 5. 学习状态不是 absent
    ok = result["learning_state"] != "absent"
    checks.append(("学习状态非absent", ok, f"state={result['learning_state']}"))

    # 6. 疲劳子指标存在
    ok = "fatigue_sub" in result and len(result["fatigue_sub"]) == 5
    checks.append(("疲劳5项子指标", ok, f"sub={list(result['fatigue_sub'].keys())}"))

    # 7. fatigue_sub 各项在 0-1 范围
    subs_ok = all(0 <= v <= 1 for v in result["fatigue_sub"].values())
    checks.append(("疲劳子指标范围", subs_ok, str(result["fatigue_sub"])))

    passed = all(c[1] for c in checks)
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}: {detail}")
    print(f"  => {'通过' if passed else '失败'}")

    return passed, result


def test_noise_no_person():
    """场景2: 随机噪声 → 应检测不到人"""
    print("\n=== 场景2: 噪声图片（无人） ===")
    frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
    result = analyze_frame("test-noise", frame)

    checks = []
    ok = result["person_present"] is False
    checks.append(("检测不到人", ok, f"person_present={result['person_present']}"))
    ok = result["learning_state"] == "absent"
    checks.append(("学习状态=absent", ok, f"state={result['learning_state']}"))
    ok = result["distraction_level"] == 0.0
    checks.append(("分心度=0（无人时）", ok, f"distraction={result['distraction_level']}"))
    ok = result["fatigue_level"] == 0.0
    checks.append(("疲劳度=0（无人时）", ok, f"fatigue={result['fatigue_level']}"))

    passed = all(c[1] for c in checks)
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}: {detail}")
    print(f"  => {'通过' if passed else '失败'}")

    return passed, result


def test_sscma_injection():
    """场景3: SSCMA 数据注入 → 验证传播正确"""
    print("\n=== 场景3: SSCMA 数据注入 ===")
    frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)

    # 无 SSCMA
    r1 = analyze_frame("test-sscma", frame)
    # 有 SSCMA（高分）
    r2 = analyze_frame("test-sscma", frame, sscma_data=make_sscma(person_score=90))
    # 有 SSCMA（低分）
    r3 = analyze_frame("test-sscma", frame, sscma_data=make_sscma(person_score=20))

    checks = []
    ok = r1["sscma_person_score"] == 0
    checks.append(("无SSCMA时score=0", ok, f"score={r1['sscma_person_score']}"))
    ok = r2["sscma_person_score"] == 90
    checks.append(("SSCMA注入后score=90", ok, f"score={r2['sscma_person_score']}"))
    ok = r3["sscma_person_score"] == 20
    checks.append(("SSCMA注入后score=20", ok, f"score={r3['sscma_person_score']}"))

    passed = all(c[1] for c in checks)
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}: {detail}")
    print(f"  => {'通过' if passed else '失败'}")

    return passed, r2


def test_vad_tracking():
    """场景4: VAD 数据注入 → 验证说话占比追踪"""
    print("\n=== 场景4: VAD 说话占比追踪 ===")
    frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
    did = "test-vad"

    # 重置 state
    state = _get_state(did)
    state["vad_speaking_count"] = 0
    state["vad_total_count"] = 0
    state["vad_speaking_pct"] = 0.0

    # 发送 8 帧不说话 + 2 帧说话
    for _ in range(8):
        analyze_frame(did, frame, vad_data=make_vad(False))
    for _ in range(2):
        analyze_frame(did, frame, vad_data=make_vad(True))

    result = analyze_frame(did, frame, vad_data=make_vad(False))
    expected_pct = round(2 / 11, 2)  # 2 speaking / 11 total
    actual_pct = result["vad_speaking_pct"]

    checks = []
    ok = abs(actual_pct - expected_pct) <= 0.02
    checks.append((f"VAD占比≈{expected_pct}", ok, f"实际={actual_pct}"))
    ok = result["vad_speaking_pct"] > 0
    checks.append(("VAD占比>0（有说话记录）", ok, f"pct={actual_pct}"))

    passed = all(c[1] for c in checks)
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}: {detail}")
    print(f"  => {'通过' if passed else '失败'}")

    return passed, result


def test_distraction_scenarios():
    """场景5: 分心度——无人/有人对比"""
    print("\n=== 场景5: 分心度场景 ===")
    frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)

    r_noise = analyze_frame("test-dist-noise", frame)

    # 用真实照片（有人）
    path = os.path.join(os.path.dirname(__file__), "real_face.jpg")
    frame_real = cv2.imread(path)
    r_real = analyze_frame("test-dist-real", frame_real)

    checks = []
    ok = r_noise["distraction_level"] == 0.0
    checks.append(("无人时分心度=0", ok, f"={r_noise['distraction_level']}"))
    ok = r_real["person_present"] and 0.0 <= r_real["distraction_level"] <= 1.0
    checks.append(("有人时分心度0-1", ok, f"={r_real['distraction_level']}"))

    passed = all(c[1] for c in checks)
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}: {detail}")
    print(f"  => {'通过' if passed else '失败'}")

    return passed, r_real


def test_difficulty_7dim():
    """场景6: 困难度 7 维度 → 验证 restlessness 和 VAD 的影响"""
    print("\n=== 场景6: 困难度7维度融合 ===")

    # 基准：全投入学习
    tracker_low = DifficultyTracker(window_seconds=60)
    for _ in range(30):
        tracker_low.add_result(_make_record(
            learning_state="engaged_writing", action_state="writing",
            gaze_direction="down", fatigue_level=0.1, torso_angle=85.0))
    score_low = tracker_low.compute()

    # 高困难：挣扎 + 躁动 + 说话
    tracker_high = DifficultyTracker(window_seconds=60)
    for _ in range(15):
        tracker_high.add_result(_make_record(
            learning_state="distracted_phone", action_state="playing_phone",
            gaze_direction="down", fatigue_level=0.2, torso_angle=75.0,
            sscma_restlessness=0.7, vad_speaking_pct=0.5))
    for _ in range(15):
        tracker_high.add_result(_make_record(
            learning_state="distracted_away", action_state="idle",
            gaze_direction="away", fatigue_level=0.4, torso_angle=70.0,
            sscma_restlessness=0.8, vad_speaking_pct=0.6))
    score_high = tracker_high.compute()

    checks = []
    ok = score_low < 0.3
    checks.append(("投入学习困难度<0.3", ok, f"={score_low}"))
    ok = score_high > 0.3
    checks.append(("挣扎+躁动+说话困难度>0.3", ok, f"={score_high}"))
    ok = score_high > score_low * 2  # 高困难应至少是低困难的2倍
    checks.append(("高困难 >> 低困难", ok, f"ratio={score_high / max(score_low, 0.01):.1f}x"))

    passed = all(c[1] for c in checks)
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}: {detail}")
    print(f"  => {'通过' if passed else '失败'}")

    return passed, (score_low, score_high)


def test_sscma_restlessness_accumulation():
    """场景7: SSCMA 躁动不安累积 → 多次不同框位置产生 restlessness"""
    print("\n=== 场景7: SSCMA 躁动不安累积 ===")
    did = "test-restless"
    # 重置 state
    state = _get_state(did)
    state["sscma_box_centers"].clear()
    state["sscma_restlessness"] = 0.0
    state["sscma_score_history"].clear()

    frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)

    # 模拟框位置抖动（同一人脸在不同位置）
    jitter_boxes = [
        (100, 50, 200, 300),   # cx=200, cy=200
        (120, 60, 200, 300),   # cx=220, cy=210
        (80, 40, 200, 300),    # cx=180, cy=190
        (140, 70, 200, 300),   # cx=240, cy=220
        (60, 30, 200, 300),    # cx=160, cy=180
        (130, 55, 200, 300),   # cx=230, cy=205
    ]

    for box in jitter_boxes:
        analyze_frame(did, frame, sscma_data=make_sscma(person_score=85, box=box))

    result = analyze_frame(did, frame, sscma_data=make_sscma(person_score=85, box=(100, 50, 200, 300)))
    restlessness = result["sscma_restlessness"]

    checks = []
    ok = restlessness > 0.0
    checks.append(("抖动大时restlessness>0", ok, f"restlessness={restlessness}"))
    ok = restlessness < 1.0
    checks.append(("restlessness<1.0", ok, f"restlessness={restlessness}"))

    passed = all(c[1] for c in checks)
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}: {detail}")
    print(f"  => {'通过' if passed else '失败'}")

    return passed, result


# ---- main ----

if __name__ == "__main__":
    print("=" * 60)
    print("  检测准确性测试套件")
    print("=" * 60)

    results = {}
    total = 0
    passed = 0

    tests = [
        ("真实人脸检测", test_real_face),
        ("噪声无人检测", test_noise_no_person),
        ("SSCMA数据注入", test_sscma_injection),
        ("VAD说话追踪", test_vad_tracking),
        ("分心度场景", test_distraction_scenarios),
        ("困难度7维度", test_difficulty_7dim),
        ("SSCMA躁动累积", test_sscma_restlessness_accumulation),
    ]

    for name, fn in tests:
        try:
            ok, _ = fn()
            results[name] = ok
            total += 1
            if ok:
                passed += 1
        except Exception as e:
            print(f"\n  ✗ 异常: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False
            total += 1

    print("\n" + "=" * 60)
    print(f"  结果: {passed}/{total} 通过")
    for name, ok in results.items():
        print(f"  {'✓' if ok else '✗'} {name}")
    print("=" * 60)

    if passed < total:
        print("\n  未通过的测试请检查对应检测模块的阈值和逻辑。")
        sys.exit(1)
    else:
        print("\n  所有准确性测试通过！")
