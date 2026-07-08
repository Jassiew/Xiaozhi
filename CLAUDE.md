# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run / Test

```bash
# Install dependencies
pip install -r requirements.txt

# Start backend (opens browser to http://localhost:8000 automatically)
python main.py

# Run all tests
pytest tests/ -v

# Run a single test
pytest tests/test_api.py::test_login_success -v

# End-to-end test (requires running backend)
python tests/test_e2e.py
```

No lint or format config exists. Python files use 4-space indentation, tabs in HTML/JS.

## Architecture

```
Device (小智端) ──WebSocket──▶ ws_handler.py ──┐
Device (小智端) ──HTTP POST─▶ /upload/frame ──┤
                                               ▼
                                       frame_queue (asyncio.Queue, max 50)
                                               │
                                               ▼
                                       analyzer.py (run_analyzer loop)
                                       │  MediaPipe FaceMesh + Pose
                                       │  + SSCMA auxiliary data (Phase 1)
                                       │  + VAD voice activity (Phase 3)
                                       │  calc_fatigue / calc_distraction
                                       │  calc_gaze_direction / calc_action_state
                                       │  difficulty.py (60s sliding window)
                                       │  _build_status_message() — learning_state → (emoji, text, alert)
                                               │
                                      ┌────────┼────────┐
                                      ▼        ▼        ▼
                                    MySQL   output_queue (asyncio.Queue, max 100)
                                              │
                                              ▼
                                    ws_handler._broadcast_results()
                                              │
                                              ▼ (WebSocket JSON)
                                    Device (小智端) screen update
                                    SetEmotion() + SetChatMessage() + SetStatus()
```

**Data flow (bidirectional):**
1. ESP32 sends frames via WebSocket → `ws_handler.py` → `frame_queue`. Frame JSON now includes optional `sscma` field with AI co-processor detection data and `vad` field with voice activity status.
2. `analyzer.py` runs MediaPipe, computes results, writes to MySQL. SSCMA data is used as auxiliary signal for person presence cross-validation and restlessness tracking. VAD data is used for speaking-time-based distraction detection.
3. `analyzer.py` also pushes `learning_status` JSON to `output_queue`
4. `ws_handler._broadcast_results()` reads from queue, sends to device via WebSocket
5. ESP32 `OnMonitorWsData()` callback parses JSON, updates screen emoji + text

**Key files:**
- `main.py` — FastAPI app, lifespan starts `run_analyzer` + `_broadcast_results` background tasks, serves `static/` dir
- `analyzer.py` — All detection algorithms: EAR-based fatigue, geometry-based head-pose distraction (facial landmark ratios, no camera intrinsics needed), Pose-based action classification. Accepts optional `sscma_data` dict for person presence cross-validation with SSCMA AI co-processor, and `vad_data` for voice activity tracking. `_build_status_message()` maps 9 learning states to device emoji/text/alert. `run_analyzer()` accepts `output_queue` and pushes status messages.
- `difficulty.py` — `DifficultyTracker` class: 60s window of `(action_state, gaze_direction, sscma_restlessness, vad_speaking_pct)`, scores across 7 dimensions with weighted fusion.
- `ws_handler.py` — WebSocket endpoint at `/ws/device`, HTTP multipart upload at `/upload/frame`. Maintains `_device_ws` dict (device_id→WebSocket). Parses `sscma` and `vad` fields from incoming frame JSON. `_broadcast_results()` reads from `output_queue` and pushes to devices.
- `api_router.py` — `/api/login`, `/api/devices`, `/api/sessions`, `/api/sessions/{id}`, `/api/realtime/{device_id}`, `/api/frame-image`; all auth-protected. Summary stats exclude `person_present=0` frames.
- `db.py` — `get_connection()` returns a pymysql `DictCursor` connection (synchronous, used everywhere)
- `models.py` — SQLAlchemy ORM definitions (used only for table creation via `init_db`; runtime queries use raw SQL via `db.py`)
- `config.py` — All settings from env vars; defaults: port 8000, MySQL root/root@localhost:3306/student_monitor, admin/admin123, `ABSENCE_GRACE_S=15`, `SESSION_MAX_MINUTES=10`

**ESP32 files (in `../xiaozhi-esp32-main/main/`):**
- `student_monitor.cc` — Camera capture task with WebSocket upload to backend. Includes SSCMA detection data (`sscma` field in JSON) from AI co-processor every 3 frames, and VAD voice activity (`vad` field). `OnMonitorWsData()` callback receives `learning_status` JSON and updates display via `SetEmotion()` / `SetChatMessage()` / `SetStatus()`.
- `application.cc` — Main application loop, state machine. `Alert()` method plays OGG sound + updates display (available for future voice alerts).
- `display/lcd_display.cc` — LVGL UI layout: emoji box, status bar, chat message area, preview image, monitor message label (centered multiline).
- `display/lvgl_display/emoji_collection.h` — Twemoji32/64: 21 emotion names (neutral, happy, cool, thinking, shocked, confused, sleepy, etc.)
- `boards/common/camera.h` — Camera base class with virtual methods: `GetSscmaDetectionJson()` and `RefreshDetection()` (default no-op).
- `boards/sensecap-watcher/sscma_camera.h` — SenseCAP Watcher camera with Himax SSCMA AI co-processor. `SscmaDetectionCache` struct caches latest inference results (person box, score, model type). Overrides `GetSscmaDetectionJson()` and `RefreshDetection()`.
- `boards/sensecap-watcher/sscma_camera.cc` — Camera capture (640×480 JPEG) and AI inference (416×416 person detection). `on_event` callback caches detection results thread-safely. `RefreshDetection()` runs single-shot inference between capture frames.

## Detection modules

MediaPipe runs **once per frame** for each model (FaceMesh ×1, Pose ×1). Results are shared across all detectors — no redundant inference.

| Module | Output | Range / Values | Key thresholds |
|--------|--------|----------------|----------------|
| `calc_fatigue()` | dict | `fatigue_level` 0.0–1.0, `fatigue_sub` with 5 sub-scores | 6-indicator fusion: EAR(0.25) + PERCLOS(0.30) + MAR/yawn(0.20) + head-nod(0.15) + blink-rate(0.10) + SSCMA restlessness boost |
| `calc_distraction()` | float | 0.0–1.0 (0.0 when no face) | head deviation ≤15°=0, ≥45°=1 |
| `calc_gaze_direction()` | string | `screen` / `away` / `down` / `up` | yaw±35°, pitch±20° (auto-calibrated) |
| `calc_action_state()` | string | `writing` / `playing_phone` / `lying_down` / `reading` / `idle` | torso angle 25°, wrist/shoulder/nose heuristics, hand-height-diff for one-handed phone |
| `calc_learning_state()` | string | 9 states (see below) | Multi-dimensional: action + gaze + duration + fatigue. 2s debounce on state transitions. |
| `DifficultyTracker.compute()` | float | 0.0–1.0 | 60s window, min 5 records, 7-dimension weighted fusion |
| `_build_status_message()` | dict | `{type, learning_state, emotion, message, alert, ...}` | Maps 9 learning states → device emoji name, screen text, voice alert flag. Used by `output_queue` for bidirectional WebSocket push. |

Learning states: `engaged_screen`, `engaged_writing`, `engaged_reading`, `thinking`, `distracted_phone`, `distracted_away`, `fatigued`, `resting`, `absent`

### SSCMA AI co-processor integration (Phase 1)

The SenseCAP Watcher has a Himax SSCMA AI chip that runs vision models on-device via SPI. Phase 1 integrates SSCMA person detection as auxiliary input to the backend analysis pipeline.

**ESP32 side:**
- `SscmaCamera::RefreshDetection()` — Called every 3 frames (~3s) between JPEG captures. Switches sensor to 416×416, runs single-shot inference on model 4 (person detection), caches results via `on_event` callback.
- `SscmaCamera::GetSscmaDetectionJson()` — Thread-safe accessor that serializes the cached `SscmaDetectionCache` to JSON.
- Frame JSON format: `{"type":"frame","image":"...","timestamp":...,"device_id":"...","sscma":{"person_detected":true,"person_score":85,"box":{"x":100,"y":50,"w":200,"h":300},"model_type":0,"point_count":0}}`
- On first frame (before any `RefreshDetection` call) or non-Watcher devices, `sscma` field is `{}`.

**Backend side:**
- `ws_handler._process_frame()` — Parses `sscma` field from incoming JSON, attaches to frame queue payload.
- `analyzer.analyze_frame(sscma_data)` — Accepts optional SSCMA dict. Uses `person_score` for cross-validation with MediaPipe face detection.
- `analyzer._write_db()` — SSCMA-assisted absence tracking: when MediaPipe says no person but SSCMA `person_score > 85`, the absence grace period is doubled (15s → 30s) to prevent false session breaks from missed face detections.
- Result dict includes `sscma_person_score` field (0 when no SSCMA data).

**Sensor mode switching:** Capture (640×480) and inference (416×416) share the same SSCMA client and cannot run simultaneously. `RefreshDetection()` switches to 416×416 for inference; the next `Capture()` switches back to 640×480 for JPEG capture. Both are serialized via `capture_mutex_`.

### SSCMA restlessness (Phase 2)

Uses SSCMA person bounding box jitter as a fatigue/difficulty auxiliary signal:
- `_update_sscma_state()` — Tracks `person_score` history (30 samples) and box center positions (30 samples). Computes restlessness as normalized std dev of box centers (0–50px → 0.0–1.0).
- `calc_fatigue()` — SSCMA restlessness as matching boost: when core fatigue > 0.3 AND restlessness > 0.5, adds up to 0.075 to fatigue level (body fidgeting = fatigue confirmation signal).
- `DifficultyTracker` — restlessness as 6th dimension (weight 0.08): high restlessness during study = difficulty/frustration indicator.

### VAD voice activity detection (Phase 3)

ESP32 reports VAD speaking status with each frame. Used as auxiliary distraction/difficulty signal:
- `student_monitor.cc` — Samples `Application::IsVoiceDetected()` each frame, includes `{"vad":{"speaking":bool}}` in WebSocket JSON.
- `analyzer._get_state()` — Tracks `vad_speaking_count` / `vad_total_count` → `vad_speaking_pct` (rolling ratio).
- `DifficultyTracker` — VAD speaking % as 7th dimension (weight 0.07): frequent talking during study = potential distraction/difficulty.
- Touch events NOT available on SenseCAP Watcher (uses knob/button, not a touch screen). Touch is deferred to future device support.
- VAD is driven by ESP-SR AFE audio processor. Available whenever audio is active (wake word listening during idle state).

### Session management (`_write_db` in analyzer.py)

- **Absence tracking**: Per-device `_absence_state` dict tracks `absence_start` and `session_ended`. When `person_present=False` for > `ABSENCE_GRACE_S` (15s, or 30s if SSCMA still detects a person with score >85), current session ends with `end_time = absence_start`. Absent frames after session ends are not written to DB. When person returns, a new session auto-creates.
- **Max duration**: Sessions also auto-end and restart after `SESSION_MAX_MINUTES` (10 min).
- **Summary filtering**: `api_router.py` summary calculations (`avg_fatigue`, `avg_distraction`, `avg_difficulty`) exclude `person_present=0` frames, preventing absent-period default values from polluting statistics.

### Fatigue sub-indicators

| Indicator | Weight | Source | Meaning |
|-----------|--------|--------|---------|
| EAR | 0.25 | FaceMesh eye landmarks | Eye Aspect Ratio — lower = more closed |
| PERCLOS | 0.30 | 60s EAR closure window | % of time eyes ≥80% closed |
| MAR | 0.20 | FaceMesh mouth landmarks | Mouth Aspect Ratio — yawning detection |
| Head nod | 0.15 | pitch time-series | Sudden head drops = microsleep |
| Blink rate | 0.10 | EAR waveform transients | Normal 15-20/min; fatigue >25 or <8 |
| SSCMA restlessness | boost | SSCMA box center jitter | Body fidgeting confirmation signal (Phase 2) |

### Difficulty sub-dimensions

| Dimension | Weight | Source | Meaning |
|-----------|--------|--------|---------|
| Struggle ratio | 0.25 | learning_state in STRUGGLE_STATES | % time in distracted/fatigued/resting |
| Volatility | 0.20 | State transition count | Frequent state switching = unable to focus |
| Fatigue drift | 0.18 | Mean fatigue_level | Average fatigue over window |
| Blank stare | 0.13 | Consecutive idle+screen pairs | Staring blankly without interaction |
| Posture decline | 0.09 | Torso angle linear regression | Negative slope = slouching over time |
| Restlessness | 0.08 | SSCMA box center jitter (Phase 2) | Body fidgeting = difficulty signal |
| VAD speaking | 0.07 | VAD speaking time % (Phase 3) | Frequent talking = distraction signal |

Head pose uses geometry-based estimation (facial landmark ratios: nose-tip offset for yaw, nose-vs-eyes for pitch). No camera intrinsics needed — works across different camera modules.

## Time handling

All timestamps are **UTC** in the database (MySQL `DATETIME` columns, populated via `datetime.now(timezone.utc)`). `api_router.py` has an `_iso()` helper that attaches `+00:00` timezone info before serialization so the JavaScript frontend parses them correctly and displays in the browser's local timezone (Beijing = UTC+8).

`ws_handler.py:18` uses `datetime.now()` (naive, local time) for directory naming only — this is intentional so saved frame folders match the user's wall-clock date.

## Database

MySQL, database name `student_monitor`. Three tables (see `models.py` for schema):
- `devices` — device registry with bind_code
- `sessions` — learning sessions (active/ended), linked to analysis_results
- `analysis_results` — per-frame analysis output, 1 row per processed frame

Runtime uses raw SQL via `pymysql` with `DictCursor`. The SQLAlchemy `models.py` is only for initial table creation. There is no migration system.
