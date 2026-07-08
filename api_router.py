"""REST API：登录、设备管理、时段查询、实时数据"""
from datetime import datetime, timedelta, timezone
import os
import random
import json
from fastapi import APIRouter, Depends, HTTPException, Query as FastAPIQuery
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from jose import jwt, JWTError
from passlib.context import CryptContext
from db import get_connection
from config import (
    JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINUTES,
    ADMIN_USERNAME, ADMIN_PASSWORD, FRAME_SAVE_DIR
)

router = APIRouter(prefix="/api")
security = HTTPBearer()
security_loose = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_admin_password_hash = pwd_context.hash(ADMIN_PASSWORD)

# MySQL DATETIME 不保存时区，pymysql 返回的是 naive datetime，
# 但实际存的是 UTC 时间，需要补上时区标识给前端 JS 正确解析
def _iso(ts):
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.isoformat()


# --- 认证 ---

@router.post("/login")
async def login(body: dict):
    username = body.get("username", "")
    password = body.get("password", "")
    if username != ADMIN_USERNAME:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not pwd_context.verify(password, _admin_password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    token = jwt.encode({"sub": username, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if username != ADMIN_USERNAME:
            raise HTTPException(status_code=401)
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的认证令牌")


async def get_current_user_loose(
    credentials: HTTPAuthorizationCredentials = Depends(security_loose),
    token: str = FastAPIQuery(None),
):
    """同时支持 Header 和 Query 参数认证（用于 <img> 标签等无法自定义 Header 的场景）"""
    raw = None
    if credentials and credentials.credentials:
        raw = credentials.credentials
    elif token:
        raw = token
    else:
        raise HTTPException(status_code=401, detail="缺少认证令牌")
    try:
        payload = jwt.decode(raw, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if username != ADMIN_USERNAME:
            raise HTTPException(status_code=401)
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的认证令牌")


# --- 设备管理 ---

@router.get("/devices")
async def list_devices(user: str = Depends(get_current_user)):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, device_id, name, created_at FROM devices ORDER BY created_at DESC")
            rows = cur.fetchall()
        return [{"id": r["id"], "device_id": r["device_id"], "name": r["name"],
                 "created_at": _iso(r["created_at"])} for r in rows]
    finally:
        conn.close()


@router.post("/devices/bind")
async def bind_device(body: dict, user: str = Depends(get_current_user)):
    device_id = body.get("device_id", "").strip()
    bind_code = body.get("bind_code", "").strip()
    name = body.get("name", "").strip()

    if not device_id:
        raise HTTPException(status_code=400, detail="device_id 不能为空")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM devices WHERE device_id = %s", (device_id,))
            existing = cur.fetchone()

            if existing:
                if existing["bind_code"] and existing["bind_code"] != bind_code:
                    raise HTTPException(status_code=403, detail="绑定码错误")
            else:
                code = bind_code or f"{random.randint(1000, 9999)}"
                cur.execute(
                    "INSERT INTO devices (device_id, name, bind_code) VALUES (%s, %s, %s)",
                    (device_id, name or device_id, code)
                )
                conn.commit()
                return {"status": "bound", "bind_code": code}
    finally:
        conn.close()
    return {"status": "ok"}


# --- 学习时段 ---

@router.get("/sessions")
async def list_sessions(device_id: str = "", user: str = Depends(get_current_user)):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if device_id:
                cur.execute(
                    "SELECT * FROM sessions WHERE device_id = %s ORDER BY start_time DESC LIMIT 50",
                    (device_id,)
                )
            else:
                cur.execute("SELECT * FROM sessions ORDER BY start_time DESC LIMIT 50")
            rows = cur.fetchall()
        return [
            {"id": r["id"], "device_id": r["device_id"],
             "start_time": _iso(r["start_time"]), "end_time": _iso(r["end_time"]),
             "status": r["status"]}
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: int,
    from_time: str = None,
    to_time: str = None,
    max_points: int = 100,
    user: str = Depends(get_current_user)
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
            session = cur.fetchone()
            if session is None:
                raise HTTPException(status_code=404, detail="时段不存在")

            # 解析时间筛选参数（兼容 JS toISOString 的 Z 后缀和 Python 3.10）
            from_dt = None
            to_dt = None
            if from_time:
                from_dt = datetime.fromisoformat(from_time.replace("Z", "+00:00"))
                if from_dt.tzinfo is not None:
                    from_dt = from_dt.replace(tzinfo=None)  # MySQL DATETIME 无时区
            if to_time:
                to_dt = datetime.fromisoformat(to_time.replace("Z", "+00:00"))
                if to_dt.tzinfo is not None:
                    to_dt = to_dt.replace(tzinfo=None)

            # 构建 SQL：时间范围筛选
            if from_dt and to_dt:
                cur.execute(
                    "SELECT * FROM analysis_results WHERE session_id = %s AND timestamp >= %s AND timestamp <= %s ORDER BY timestamp",
                    (session_id, from_dt, to_dt)
                )
            elif from_dt:
                cur.execute(
                    "SELECT * FROM analysis_results WHERE session_id = %s AND timestamp >= %s ORDER BY timestamp",
                    (session_id, from_dt)
                )
            elif to_dt:
                cur.execute(
                    "SELECT * FROM analysis_results WHERE session_id = %s AND timestamp <= %s ORDER BY timestamp",
                    (session_id, to_dt)
                )
            else:
                cur.execute(
                    "SELECT * FROM analysis_results WHERE session_id = %s ORDER BY timestamp",
                    (session_id,)
                )
            results = cur.fetchall()

        # 全量记录数（不含时间筛选）
        total = len(results)

        # 降采样到 max_points
        timeline = _build_trend(results, max_points)

        # 计算筛选范围内的摘要（排除无人帧，避免默认分心值污染统计）
        filtered_count = len(results)
        present_results = [r for r in results if r.get("person_present", 1)]
        summary = None
        if present_results:
            summary = {
                "avg_fatigue": round(sum(r["fatigue_level"] for r in present_results) / len(present_results), 2),
                "avg_distraction": round(sum(r["distraction_level"] for r in present_results) / len(present_results), 2),
                "avg_difficulty": round(sum(r["difficulty_indicator"] for r in present_results) / len(present_results), 2),
                "max_difficulty": round(max(r["difficulty_indicator"] for r in present_results), 2),
                "frame_count": filtered_count,
            }

        # 提取事件（无人时不产生告警），倒序遍历=最新在前
        # 事件标签基于 learning_state，比单纯阈值更有可读性
        events = []
        for r in reversed(results):
            is_present = r.get("person_present", 1)
            if not is_present:
                continue
            ts = _iso(r["timestamp"])
            fp = r.get("raw_frame_path", "")
            ls = r.get("learning_state", "")
            action = r.get("action_state", "")

            # 按学习状态生成具体标签
            label = None
            etype = None
            detail = None

            if ls == "distracted_phone":
                label = "玩手机 📱"
                etype = "distraction"
                detail = "检测到手机使用行为"
            elif ls == "distracted_away":
                label = "注意力分散"
                etype = "distraction"
                detail = "视线偏离屏幕"
            elif ls == "fatigued":
                label = "疲劳 😴"
                etype = "fatigue"
                detail = "疲劳指标偏高"
            elif ls == "resting":
                label = "趴桌休息 💤"
                etype = "fatigue"
                detail = "学生趴下休息"
            elif r["difficulty_indicator"] > 0.5:
                label = "困难度升高"
                etype = "difficulty"
                detail = "学习内容可能偏难"
            elif r["fatigue_level"] > 0.5:
                label = "疲劳趋势"
                etype = "fatigue"
                detail = "疲劳度上升中"
            elif r["distraction_level"] > 0.5:
                label = "分心趋势"
                etype = "distraction"
                detail = "注意力持续下降"

            if label:
                events.append({"timestamp": ts, "type": etype, "label": label, "detail": detail, "frame_path": fp})

        # 离开统计
        away_count = sum(1 for r in results if not r.get("person_present", 1)) if results else 0
        if summary and filtered_count > 0:
            summary["away_pct"] = round(away_count / filtered_count * 100, 1)

        # 状态分布（饼图用）— 跳过无有效 learning_state 的旧记录
        from collections import Counter
        state_counts = Counter(
            r.get("learning_state") for r in results
            if r.get("person_present", 1) and r.get("learning_state")
        )
        total_present = sum(state_counts.values()) or 1
        state_distribution = {
            state: round(count / total_present * 100, 1)
            for state, count in state_counts.most_common()
        }

        return {
            "id": session["id"], "device_id": session["device_id"],
            "start_time": _iso(session["start_time"]),
            "end_time": _iso(session["end_time"]),
            "status": session["status"],
            "timeline": timeline,
            "total_records": total,
            "summary": summary,
            "state_distribution": state_distribution,
            "events": events,
        }
    finally:
        conn.close()


@router.get("/overview/today")
async def get_today_overview(user: str = Depends(get_current_user)):
    """今日概览：学习时长、专注率、告警次数、活跃设备数"""
    conn = get_connection()
    try:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        # MySQL DATETIME 无时区
        today_start_naive = today_start.replace(tzinfo=None)

        with conn.cursor() as cur:
            # 活跃设备数（今天有上报过的设备）
            cur.execute(
                """SELECT COUNT(DISTINCT device_id) as cnt FROM sessions
                   WHERE start_time >= %s""",
                (today_start_naive,)
            )
            active_devices = cur.fetchone()["cnt"] or 0

            # 今日学习时段
            cur.execute(
                """SELECT id, device_id, start_time, end_time, status FROM sessions
                   WHERE start_time >= %s ORDER BY start_time""",
                (today_start_naive,)
            )
            sessions = cur.fetchall()

            # 统计
            total_learning_sec = 0
            total_frames = 0
            alert_count = 0
            engaged_frames = 0
            present_frames = 0

            for s in sessions:
                sid = s["id"]
                cur.execute(
                    "SELECT * FROM analysis_results WHERE session_id = %s ORDER BY timestamp",
                    (sid,)
                )
                results = cur.fetchall()

                for r in results:
                    if not r.get("person_present", 1):
                        continue
                    present_frames += 1
                    total_frames += 1

                    ls = r.get("learning_state", "")
                    if ls.startswith("engaged"):
                        engaged_frames += 1
                    if ls in ("distracted_phone", "distracted_away", "fatigued"):
                        alert_count += 1

                # 学习时长（有人帧 × 帧间隔约 6 秒估算，或直接按时段长度）
                if s["end_time"] and s["start_time"]:
                    total_learning_sec += (s["end_time"] - s["start_time"]).total_seconds()
                elif s["start_time"]:
                    total_learning_sec += (datetime.now(timezone.utc).replace(tzinfo=None) - s["start_time"]).total_seconds()

            total_minutes = round(total_learning_sec / 60)
            focus_rate = round(engaged_frames / max(present_frames, 1) * 100)

        return {
            "active_devices": active_devices,
            "total_minutes": total_minutes,
            "total_sessions": len(sessions),
            "alert_count": alert_count,
            "focus_rate": focus_rate,
        }
    finally:
        conn.close()


@router.get("/realtime/{device_id}")
async def get_realtime(device_id: str, user: str = Depends(get_current_user)):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM sessions WHERE device_id = %s AND status = 'active' ORDER BY start_time DESC LIMIT 1",
                (device_id,)
            )
            session_row = cur.fetchone()

            if session_row is None:
                return {"online": False, "session": None, "summary": {}, "trend": []}

            ten_min_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
            cur.execute(
                "SELECT * FROM analysis_results WHERE session_id = %s AND timestamp >= %s ORDER BY timestamp",
                (session_row["id"], ten_min_ago)
            )
            recent = cur.fetchall()

            if not recent:
                return {"online": True, "session_id": session_row["id"], "summary": {}, "trend": []}

            # 1分钟汇总（卡片用）
            one_min_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
            # pymysql 返回 naive datetime，补时区后筛选
            last_min = []
            for r in recent:
                ts = r["timestamp"]
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= one_min_ago:
                    last_min.append(r)
            if not last_min:
                last_min = recent[-5:] if len(recent) >= 5 else recent

            present_min = [r for r in last_min if r.get("person_present", 1)]
            if not present_min:
                present_min = last_min

            avg_fatigue = sum(r["fatigue_level"] for r in present_min) / len(present_min)
            avg_distraction = sum(r["distraction_level"] for r in present_min) / len(present_min)
            avg_difficulty = sum(r["difficulty_indicator"] for r in present_min) / len(present_min)
            latest = last_min[-1]

            # 10分钟趋势（30秒桶采样，最多20个点）
            trend = _build_trend(recent)

            # 最近告警（5条，连续同类型合并去重，取最新）
            alert_states = {"distracted_phone", "distracted_away", "fatigued"}
            all_runs = []
            current_run = None  # {learning_state, start_ts, end_ts, fatigue_sum, distraction_sum, count}

            for r in recent:
                ls = r.get("learning_state", "")
                ts = r["timestamp"]
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                if ls in alert_states and r.get("person_present", 1):
                    if current_run and current_run["learning_state"] == ls:
                        current_run["end_ts"] = ts
                        current_run["fatigue_sum"] += r["fatigue_level"]
                        current_run["distraction_sum"] += r["distraction_level"]
                        current_run["count"] += 1
                    else:
                        if current_run:
                            all_runs.append(current_run)
                        current_run = {
                            "learning_state": ls,
                            "start_ts": ts,
                            "end_ts": ts,
                            "fatigue_sum": r["fatigue_level"],
                            "distraction_sum": r["distraction_level"],
                            "count": 1,
                        }
                else:
                    if current_run:
                        all_runs.append(current_run)
                        current_run = None

            if current_run:
                all_runs.append(current_run)

            print(f"[Alerts] {device_id}: {len(all_runs)} alert runs found in last 10min, "
                  f"keeping {min(5, len(all_runs))} most recent")

            alerts = []
            for run in all_runs[-5:]:
                cnt = run["count"]
                alerts.append({
                    "learning_state": run["learning_state"],
                    "start_time": _iso(run["start_ts"]),
                    "end_time": _iso(run["end_ts"]),
                    "duration_s": int((run["end_ts"] - run["start_ts"]).total_seconds()),
                    "frame_count": cnt,
                    "avg_fatigue": round(run["fatigue_sum"] / cnt, 2),
                    "avg_distraction": round(run["distraction_sum"] / cnt, 2),
                })

            return {
                "online": True,
                "session_id": session_row["id"],
                "device_id": device_id,
                "session_start": _iso(session_row["start_time"]),
                "summary": {
                    "avg_fatigue": round(avg_fatigue, 2),
                    "avg_distraction": round(avg_distraction, 2),
                    "avg_difficulty": round(avg_difficulty, 2),
                    "learning_state": latest.get("learning_state", ""),
                    "current_action": latest["action_state"],
                    "current_gaze": latest["gaze_direction"],
                    "person_present": bool(latest.get("person_present", 1)),
                    "sscma_person_score": latest.get("sscma_person_score", 0),
                    "vad_speaking_pct": latest.get("vad_speaking_pct", 0),
                    "sample_count": len(last_min),
                },
                "trend": trend,
                "alerts": alerts,
            }
    finally:
        conn.close()


@router.get("/frame-image")
async def serve_frame_image(path: str = FastAPIQuery(...), user: str = Depends(get_current_user_loose)):
    """Serve a saved frame image with path traversal protection"""
    abs_root = os.path.abspath(FRAME_SAVE_DIR)
    abs_path = os.path.abspath(path)
    if not abs_path.startswith(abs_root + os.sep) and abs_path != abs_root:
        raise HTTPException(status_code=403, detail="invalid path")
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(abs_path, media_type="image/jpeg")


def _build_trend(records, max_points=100):
    """将记录按分桶降采样，返回最多 max_points 个趋势点"""
    if not records:
        return []
    if len(records) <= max_points:
        return [{
            "timestamp": _iso(r["timestamp"]),
            "fatigue": r["fatigue_level"],
            "distraction": r["distraction_level"],
            "difficulty": r["difficulty_indicator"],
        } for r in records]

    step = max(1, len(records) // max_points)
    buckets = []
    for i in range(0, len(records), step):
        chunk = records[i:i + step]
        buckets.append({
            "timestamp": _iso(chunk[-1]["timestamp"]),
            "fatigue": round(sum(r["fatigue_level"] for r in chunk) / len(chunk), 2),
            "distraction": round(sum(r["distraction_level"] for r in chunk) / len(chunk), 2),
            "difficulty": round(sum(r["difficulty_indicator"] for r in chunk) / len(chunk), 2),
        })
    return buckets


# ============================================================
# Agent 对话接口
# ============================================================

from pydantic import BaseModel


class AgentChatRequest(BaseModel):
    message: str


@router.post("/agent/chat")
async def agent_chat(req: AgentChatRequest, user: str = Depends(get_current_user)):
    """Agent 对话 —— 结合行为缓冲区的结构化上下文"""
    from agent import get_agent, get_buffer
    agent = get_agent()
    snapshot = get_buffer().get_snapshot()
    reply = agent.chat(req.message, snapshot)
    return {"reply": reply}


@router.get("/agent/analyze")
async def agent_analyze(user: str = Depends(get_current_user)):
    """结构化行为分析 —— LLM 输出 JSON"""
    from agent import get_agent, get_buffer
    buffer = get_buffer()
    snapshot = buffer.get_snapshot()

    # 本地统计摘要（无需 LLM，秒出）
    summary = buffer.get_summary()

    # LLM 深度分析
    agent = get_agent()
    analysis = agent.analyze(snapshot)

    return {
        "summary": summary,
        "analysis": analysis,
        "has_data": len(snapshot) > 0,
    }
