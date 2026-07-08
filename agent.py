"""Agent 学习助手 —— LLM 行为语义分析与对话模块

升级 1: 结构化行为数据 → LLM → 结构化 JSON 分析
升级 2: BehaviorBuffer 自动采集分析器输出 → 定时触发报告

用法：
    from agent import Agent, get_agent, get_buffer, push_behavior
    agent = get_agent()
    result = agent.analyze(buffer.get_snapshot())  # 结构化分析
    reply  = agent.chat("你好", buffer.get_snapshot())  # 对话
"""

import os
import json
import threading
from datetime import datetime, timezone
from collections import deque
from openai import OpenAI

_dotenv_loaded = False


def _load_env():
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    os.environ.setdefault(key.strip(), val.strip())
    _dotenv_loaded = True


# ============================================================
# BehaviorBuffer —— 滑动窗口行为缓冲
# ============================================================

class BehaviorBuffer:
    """收集 analyzer 输出，提供结构化行为快照"""

    def __init__(self, window_sec: int = 1800):
        self.window_sec = window_sec  # 默认 30 分钟窗口
        self._buffer = deque(maxlen=2000)
        self._lock = threading.Lock()

    def push(self, record: dict):
        """推入一条分析结果"""
        with self._lock:
            self._buffer.append({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "state": record.get("learning_state", "unknown"),
                "fatigue": round(record.get("fatigue_level", 0), 2),
                "distraction": round(record.get("distraction_level", 0), 2),
                "action": record.get("action_state", ""),
                "gaze": record.get("gaze_direction", ""),
            })

    def get_snapshot(self) -> list:
        """返回窗口内所有行为记录"""
        with self._lock:
            return list(self._buffer)

    def get_summary(self) -> dict:
        """计算窗口内的统计摘要（无需 LLM，本地计算）"""
        with self._lock:
            if not self._buffer:
                return {"total_frames": 0, "duration_min": 0}

            records = list(self._buffer)
            total = len(records)
            states = [r["state"] for r in records]
            fatigues = [r["fatigue"] for r in records]
            distracts = [r["distraction"] for r in records]

            # 各状态占比
            from collections import Counter
            sc = Counter(states)
            state_pct = {k: round(v / total * 100, 1) for k, v in sc.most_common()}

            # 专注率 = engaged 状态占比
            engaged_count = sum(1 for s in states if s.startswith("engaged"))
            focus_pct = round(engaged_count / total * 100, 1)

            # 告警帧数
            alert_states = {"distracted_phone", "distracted_away", "fatigued"}
            alert_count = sum(1 for s in states if s in alert_states)

            return {
                "total_frames": total,
                "duration_min": round(total * 5 / 60, 1),  # 每帧~5秒估算
                "focus_pct": focus_pct,
                "avg_fatigue": round(sum(fatigues) / total, 2),
                "avg_distraction": round(sum(distracts) / total, 2),
                "state_distribution": state_pct,
                "alert_count": alert_count,
            }


# ============================================================
# Agent —— LLM 行为分析引擎
# ============================================================

ANALYZE_SYSTEM_PROMPT = """你是一个课堂行为分析专家。你会收到学生的学习行为结构数据，需要输出结构化的分析结果。

输入格式示例：
```
[行为序列 | 2026-07-03 14:20-14:50 | 总计180帧 | 专注率78.3% | 平均疲劳0.18 | 平均分心0.12]
状态分布: 看屏幕听课(42.1%) 写字(28.5%) 阅读(7.7%) 思考中(11.2%) 分心走神(6.8%) 疲劳(3.7%)
```

你需要返回一个严格的 JSON 对象（不要 markdown 代码块，只要纯 JSON）：
{
  "focus_trend": "上升/稳定/下降",
  "fatigue_level": "低/中/高",
  "main_activity": "主要学习活动描述",
  "risk_flags": ["需要关注的问题点"],
  "suggestion": "具体的学习建议（50字以内）",
  "summary": "一句话总结（30字以内）"
}

只输出 JSON，不要其他文字。"""

CHAT_SYSTEM_PROMPT = """你是小智伴学系统的AI学习助手。你可以分析学生的学习行为数据，帮助学生了解自己的学习状态。

你能做：
1. 根据学习行为数据（专注、分心、疲劳、阅读、写字等）分析学生学习情况
2. 给出温和、鼓励性的学习建议
3. 回答学生关于学习方法的问题
4. 语气亲切但不过分幼稚

你面对的是研究生/大学生，用平等友好的语气交流。回复简洁（200字以内），不要啰嗦。
如果没有行为数据，就做通用的学习建议。"""


class Agent:
    """LLM 行为分析 Agent"""

    def __init__(self):
        _load_env()
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self.client = None

        if self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            print(f"[Agent] DeepSeek 已就绪 (model={self.model})")
        else:
            print("[Agent] 未配置 DEEPSEEK_API_KEY，Agent 不可用")

    # ========== 升级1：结构化分析 ==========

    def analyze(self, behavior_snapshot: list) -> dict | None:
        """将结构化行为序列送入 LLM，返回 JSON 分析结果

        Args:
            behavior_snapshot: BehaviorBuffer.get_snapshot() 返回的行为列表

        Returns:
            dict: {"focus_trend", "fatigue_level", "main_activity",
                   "risk_flags", "suggestion", "summary"} 或 None
        """
        if not self.client or not behavior_snapshot:
            return None

        # 构建结构化输入
        input_text = self._build_structured_input(behavior_snapshot)

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
                    {"role": "user", "content": input_text},
                ],
                max_tokens=400,
                temperature=0.3,  # 低温度保证输出稳定
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"summary": "分析结果解析失败，请重试", "suggestion": ""}
        except Exception as e:
            print(f"[Agent] analyze 失败: {e}")
            return None

    def _build_structured_input(self, snapshot: list) -> str:
        """构建 LLM 可理解的结构化行为描述"""
        if not snapshot:
            return "（暂无学习行为数据）"

        total = len(snapshot)

        # 状态分布
        from collections import Counter
        states = [r["state"] for r in snapshot]
        sc = Counter(states)
        state_str = " ".join(
            f"{_state_cn(k)}({v / total * 100:.1f}%)"
            for k, v in sc.most_common()
        )

        # 疲劳/分心均值
        avg_fatigue = round(sum(r["fatigue"] for r in snapshot) / total, 2)
        avg_distraction = round(sum(r["distraction"] for r in snapshot) / total, 2)

        # 专注率
        engaged = sum(1 for s in states if s.startswith("engaged"))
        focus_pct = round(engaged / total * 100, 1)

        # 时间线采样（每N帧取一帧，最多15帧）
        step = max(1, total // 15)
        timeline = []
        for i in range(0, total, step):
            r = snapshot[i]
            timeline.append(
                f"{r['ts'][-8:]} | {_state_cn(r['state'])} | "
                f"疲劳:{r['fatigue']:.2f} 分心:{r['distraction']:.2f}"
            )

        return (
            f"【行为序列 | 总计{total}帧 | 专注率{focus_pct}% | "
            f"平均疲劳{avg_fatigue} | 平均分心{avg_distraction}】\n"
            f"状态分布: {state_str}\n"
            f"---时间线采样---\n" +
            "\n".join(timeline)
        )

    # ========== 对话接口 ==========

    def chat(self, message: str, snapshot: list | None = None) -> str:
        """对话接口 —— 结合行为上下文"""
        if not self.client:
            return "Agent 未配置 API Key，请在 .env 中设置 DEEPSEEK_API_KEY。"

        if snapshot:
            ctx = self._build_structured_input(snapshot)
            user_content = f"{ctx}\n\n学生问：{message}"
        else:
            user_content = f"（暂无学习行为数据）\n\n学生问：{message}"

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=500,
                temperature=0.7,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"[Agent] chat 失败: {e}")
            return f"抱歉，我暂时无法回复。（{str(e)[:100]}）"


# ============================================================
# 模块级单例
# ============================================================

_agent: Agent | None = None
_buffer: BehaviorBuffer | None = None


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent


def get_buffer() -> BehaviorBuffer:
    global _buffer
    if _buffer is None:
        _buffer = BehaviorBuffer()
    return _buffer


def push_behavior(record: dict):
    """供 analyzer.py 调用，每帧分析结果推入 buffer"""
    get_buffer().push(record)


def _state_cn(ls: str) -> str:
    return {
        "engaged_screen": "看屏幕", "engaged_writing": "写字",
        "engaged_reading": "阅读", "thinking": "思考",
        "distracted_phone": "玩手机", "distracted_away": "分心",
        "fatigued": "疲劳", "resting": "休息", "absent": "离开",
    }.get(ls, ls)
