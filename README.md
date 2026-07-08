# Student Monitor (小智学习监护系统)

Real-time AI learning state monitoring system based on computer vision, with bidirectional WebSocket communication to ESP32 devices.

## Architecture

```
Device (ESP32/小智端) ──WebSocket──▶ ws_handler.py ──┐
Device (ESP32/小智端) ──HTTP POST─▶ /upload/frame ──┤
                                                     ▼
                                             frame_queue
                                                     │
                                                     ▼
                                             analyzer.py
                                             │  MediaPipe FaceMesh + Pose
                                             │  + SSCMA AI co-processor data
                                             │  + VAD voice activity
                                                     │
                                            ┌────────┼────────┐
                                            ▼        ▼        ▼
                                          MySQL   output_queue   Device display
```

## Features

- **Fatigue Detection**: EAR, PERCLOS, MAR (yawn), head nod, blink rate, SSCMA restlessness
- **Distraction Detection**: Head pose estimation (yaw/pitch), gaze direction classification
- **Action Recognition**: Writing, reading, phone-playing, lying-down, idle
- **Difficulty Tracking**: 60s sliding window, 7-dimension weighted fusion
- **9 Learning States**: engaged_screen, engaged_writing, engaged_reading, thinking, distracted_phone, distracted_away, fatigued, resting, absent
- **SSCMA AI Co-processor**: Auxiliary person detection for cross-validation
- **VAD Voice Activity**: Speaking-time-based distraction detection

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Setup MySQL database (database: student_monitor)
# Edit config.py or set environment variables for DB credentials

# Create tables
python init_db.py

# Start backend
python main.py
# Opens browser to http://localhost:8000
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8000 | Server port |
| `DB_HOST` | localhost | MySQL host |
| `DB_PORT` | 3306 | MySQL port |
| `DB_USER` | root | MySQL user |
| `DB_PASS` | root | MySQL password |
| `DB_NAME` | student_monitor | Database name |
| `ADMIN_USER` | admin | Web UI login |
| `ADMIN_PASS` | admin123 | Web UI password |
| `ABSENCE_GRACE_S` | 15 | Seconds before session ends on absence |
| `SESSION_MAX_MINUTES` | 10 | Max session duration |

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run a single test
pytest tests/test_api.py::test_login_success -v

# End-to-end test (requires running backend)
python tests/test_e2e.py
```

## ESP32 Device

The companion firmware is in the `xiaozhi-esp32` project. Key files:
- `main/student_monitor.cc` — Camera capture + WebSocket upload + display update
- `boards/sensecap-watcher/sscma_camera.cc` — SSCMA AI co-processor integration
