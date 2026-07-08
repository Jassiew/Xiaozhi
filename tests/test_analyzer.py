import numpy as np
from analyzer import analyze_frame
from difficulty import DifficultyTracker


def test_analyze_frame_returns_valid_result():
    """验证分析结果格式正确"""
    frame = np.random.randint(0, 255, (320, 240, 3), dtype=np.uint8)
    result = analyze_frame("test-device-01", frame)

    assert "fatigue_level" in result
    assert 0.0 <= result["fatigue_level"] <= 1.0
    assert "distraction_level" in result
    assert 0.0 <= result["distraction_level"] <= 1.0
    assert "gaze_direction" in result
    assert result["gaze_direction"] in ("screen", "away", "down", "up")
    assert "action_state" in result
    assert result["action_state"] in ("writing", "idle", "playing_phone", "lying_down", "reading")
    assert "learning_state" in result
    assert result["learning_state"] in (
        "engaged_screen", "engaged_writing", "engaged_reading",
        "thinking", "distracted_phone", "distracted_away",
        "fatigued", "resting", "absent",
    )
    assert "fatigue_sub" in result


def _make_record(learning_state="engaged_writing", action_state="writing",
                  gaze_direction="down", fatigue_level=0.1, torso_angle=85.0):
    return {
        "learning_state": learning_state,
        "action_state": action_state,
        "gaze_direction": gaze_direction,
        "fatigue_level": fatigue_level,
        "torso_angle": torso_angle,
    }


def test_difficulty_tracker_baseline():
    """投入学习时困难度应偏低"""
    tracker = DifficultyTracker(window_seconds=60)
    for _ in range(30):
        tracker.add_result(_make_record("engaged_writing", "writing", "down", 0.1, 85.0))
    score = tracker.compute()
    assert 0.0 <= score <= 1.0
    assert score < 0.3, f"投入学习时困难度应低，实际: {score}"


def test_difficulty_tracker_high_when_stuck():
    """长时间 idle+screen 空白凝视 + 走神 = 困难度偏高"""
    tracker = DifficultyTracker(window_seconds=60)
    for _ in range(30):
        tracker.add_result(_make_record("distracted_away", "idle", "screen", 0.4, 80.0))
    score = tracker.compute()
    assert score > 0.3, f"走神+空白凝视时困难度应偏高，实际: {score}"


def test_difficulty_tracker_high_when_struggling():
    """挣扎状态占比高时困难度应偏高"""
    tracker = DifficultyTracker(window_seconds=60)
    for _ in range(15):
        tracker.add_result(_make_record("distracted_phone", "playing_phone", "down", 0.2, 80.0))
    for _ in range(15):
        tracker.add_result(_make_record("distracted_away", "idle", "away", 0.3, 75.0))
    score = tracker.compute()
    assert score >= 0.25, f"挣扎状态过半时困难度应偏高，实际: {score}"


def test_difficulty_tracker_low_when_active():
    """正常做题时困难度应偏低"""
    tracker = DifficultyTracker(window_seconds=60)
    for _ in range(30):
        tracker.add_result(_make_record("engaged_writing", "writing", "down", 0.1, 85.0))
    score = tracker.compute()
    assert score < 0.5
