# 算法设计文档

---

## 概述

系统通过设备端摄像头采集图片，在服务端运行三个核心算法：

```
摄像头采集 → MediaPipe FaceMesh + Pose → ┌─ 疲劳检测（5指标融合）
                                          ├─ 学习状态分类（9状态）
                                          └─ 困难度评估（5维度加权）
```

三个算法**共享一次 MediaPipe 推理结果**，不做重复计算。

- **MediaPipe FaceMesh**：468 个人脸关键点
- **MediaPipe Pose**：33 个身体关键点
- **计算库**：NumPy + OpenCV（PnP 姿态估计）
- **所有指标均为公开论文公式，无需额外依赖**

---

## 一、疲劳检测

### 1.1 设计思路

疲劳检测从单一 EAR 指标升级为 **5 指标加权融合**。每个指标有公开发表的论文支撑，基于 MediaPipe 输出的关键点坐标计算。

### 1.2 融合公式

```
疲劳分 = 0.25 × EAR_score + 0.30 × PERCLOS_score + 0.20 × MAR_score + 0.15 × Nod_score + 0.10 × Blink_score
```

### 1.3 各指标详解

#### 1.3.1 EAR（眼部纵横比）— 权重 0.25

**来源**：Soukupová & Čech, "Real-Time Eye Blink Detection using Facial Landmarks" (2016)

**原理**：用 6 个眼睑关键点计算眼睛开合度。

```
EAR = (|p2-p6| + |p3-p5|) / (2 × |p1-p4|)
```

```
        p1 ←── 外眼角
       /  \
     p2    p3 ← 上眼睑
      |    |
     p6    p5 ← 下眼睑（同侧）
       \  /
        p4 ←── 内眼角
```

**阈值**：
| EAR 值 | 含义 |
|---------|------|
| >0.30 | 正常睁眼 |
| 0.20~0.30 | 半闭眼 |
| <0.20 | 闭眼 |

**评分**：
- `ear_score = max(0, (0.35 - avg_ear) / 0.15)` — 平均 EAR 越低分越高
- `close_score = min(1, 闭眼秒数 / 2.5)` — 持续闭眼 2.5 秒为严重疲劳
- `EAR_total = 0.6 × close_score + 0.4 × ear_score`

**MediaPipe 关键点**：
- 左眼：[33, 160, 158, 133, 153, 144]
- 右眼：[362, 385, 387, 263, 373, 380]

#### 1.3.2 PERCLOS（闭眼时间占比）— 权重 0.30

**来源**：Wierwille et al., FHWA Report FHWA-MC-99-133 (1999)，美国联邦公路管理局疲劳检测黄金标准

**原理**：在 60 秒滑动窗口中，统计眼睛闭合 ≥80% 的时间占比。

**判定标准**：
| PERCLOS 值 | 疲劳等级 |
|------------|----------|
| <5% | 清醒 |
| 5%~15% | 轻度疲劳 |
| 15%~30% | 中度疲劳 |
| >30% | 严重疲劳 |

**实现**：
- 每帧判断眼睛是否「≥80% 闭合」：`EAR < 当前基线 × 0.7`
- 维护 60 秒窗口内所有帧的闭合/非闭合标签
- `PERCLOS_score = min(1, PERCLOS / 0.30)` — 30% 时达到满分

**迁移说明**：驾驶场景中 PERCLOS > 15% 即触发警告；学习场景放宽到 30%，因为学习中的短暂闭眼（思考、眨眼）比驾驶中安全得多。

#### 1.3.3 MAR（嘴部纵横比 / 哈欠检测）— 权重 0.20

**来源**：同 EAR 原理，扩展到嘴部

**原理**：将 EAR 公式应用于嘴部关键点。

```
MAR = |上唇内缘 - 下唇内缘| / |左嘴角 - 右嘴角|
```

**阈值**：
| MAR 值 | 含义 |
|---------|------|
| <0.30 | 闭嘴或微张 |
| 0.30~0.55 | 说话 |
| >0.55 | 打哈欠 |

**评分**：
- `MAR_score = min(1, max(0, (avg_mar - 0.30) / 0.40))` — 0.30→0, 0.70→1.0
- 哈欠计数有 5 秒去重窗口，避免单次长哈欠被重复计数

**MediaPipe 关键点**：上唇内缘中点(13)、下唇内缘中点(14)、左嘴角内缘(78)、右嘴角内缘(308)

#### 1.3.4 头部点头（微睡眠检测）— 权重 0.15

**来源**：Bergasa et al., "Real-time system for monitoring driver vigilance" (2006)

**原理**：微睡眠时头部会突然下垂（pitch 角变小），然后迅速回弹。通过追踪头部 pitch 角的时间序列来检测。

**检测逻辑**：
1. 维护 4 秒 pitch 历史（FaceMesh PnP 姿态估计输出）
2. 若 pitch 波动范围 > 8° 且最近趋势回升 → 判定为一次点头事件
3. `Nod_score = min(1, pitch_range / 20°)` — 20° 时满分
4. 同时统计 60 秒内点头次数：>5 次/分 = 严重

#### 1.3.5 眨眼频率 — 权重 0.10

**来源**：Caffier et al., "The spontaneous eye-blink as a measure of sleepiness" (2003)

**原理**：疲劳时眨眼频率偏离正常范围。

**检测逻辑**：
- 当 EAR 在相邻帧之间下降超过 35% → 判定为一次眨眼
- 统计 60 秒内眨眼次数

**评分**：
| 眨眼频率 | 含义 | 分数 |
|----------|------|------|
| 15~22 次/分 | 正常 | 0 |
| 22~40 次/分 | 偏高（紧张/疲劳） | 0→1 线性 |
| 5~15 次/分 | 偏低（发呆/困倦） | 1→0 线性 |
| <5 次/分 | 极低（严重困倦） | 1 |

### 1.4 输出结构

```json
{
  "fatigue_level": 0.35,
  "fatigue_sub": {
    "ear": 0.28,
    "perclos": 0.42,
    "mar": 0.15,
    "nod": 0.10,
    "blink": 0.05
  }
}
```

---

## 二、学习状态分类

### 2.1 设计思路

学习的「正确行为」不只有「看屏幕」。看屏幕可能是听课，低头可能是做题，看别处可能是思考。单一维度的视线判断会把大量正常学习行为误判为分心。

**核心逻辑**：`学习状态 = f(动作状态, 视线方向, 持续时间, 疲劳度)`

### 2.2 状态定义

| 状态 | 含义 | 动作 | 视线 | 持续时间 | 疲劳 |
|------|------|------|------|----------|------|
| `engaged_screen` | 听课/看视频 | idle/reading | screen | 任意 | <0.6 |
| `engaged_writing` | 做题/写字 | writing | down | 任意 | <0.6 |
| `engaged_reading` | 阅读/看书 | reading | down | 任意 | <0.6 |
| `thinking` | 短暂思考 | idle | away/up | <30s | 任意 |
| `distracted_phone` | 玩手机 | playing_phone | 任意 | 任意 | 任意 |
| `distracted_away` | 长时间走神 | idle | away | ≥30s | <0.6 |
| `fatigued` | 疲劳需休 | 任意 | 任意 | 任意 | ≥0.6 |
| `resting` | 趴桌休息 | lying_down | 任意 | 任意 | 任意 |
| `absent` | 画面无人 | — | — | — | — |

### 2.3 状态判定优先级

```
1. absent          ← 画面无人（最高优先级）
2. resting         ← 趴桌
3. playing_phone   ← 玩手机（明确分心，无论其他信号）
4. fatigued        ← 疲劳分 ≥0.6（疲劳压倒一切）
5. distracted_away ← 走神 ≥30 秒
6. engaged_writing ← 写字+低头（学习）
7. engaged_reading ← 阅读动作+低头（学习）
8. engaged_screen  ← 看屏幕+非写字（学习）
9. thinking        ← 默认（不确定时偏向正向判断）
```

### 2.4 防抖机制

状态切换有 **2 秒防抖**：新状态必须持续 2 秒以上才会正式切换，避免在状态边界来回跳动。

### 2.5 关键设计决策

#### 为什么 `writing + down` = 学习而非分心？

做题时学生在看桌面/纸笔，视线一定是向下的。如果仅凭视线方向判断，做题会被误判为分心。但结合 Pose 检测到的手腕在肩膀以下 + 手臂位置 = writing 动作，可以确信学生正在写字。

#### 为什么 `away < 30s` = 思考而非分心？

学习中短时间看别处是正常的认知行为（回忆、思考、组织语言）。只有持续超过 30 秒的视线偏移才是真正的走神。

#### 为什么疲劳优先级高于学习状态？

一个学生可能在疲劳状态下仍然盯着屏幕，但学习效率极低。疲劳是一个根因信号，应优先发出警告。

---

## 三、困难度评估

### 3.1 设计思路

困难度衡量的是 **学生当前的「挣扎」程度**——即能否有效投入学习。与疲劳检测不同，困难度关注的是行为和状态的宏观模式，而非单帧生理信号。

### 3.2 融合公式

```
困难度 = 0.30 × struggle_ratio + 0.25 × volatility + 0.20 × fatigue_drift + 0.15 × blank_stare + 0.10 × posture_decline
```

### 3.3 各维度详解

#### 3.3.1 struggle_ratio（挣扎占比）— 权重 0.30

窗口 60 秒内，学习状态为「挣扎状态」的时间占比。

挣扎状态：`distracted_phone`、`distracted_away`、`fatigued`、`resting`

这些状态明确表示学生无法有效学习。

#### 3.3.2 volatility（状态切换度）— 权重 0.25

学习状态在窗口内的切换次数 / 最大可能切换次数。

频繁在 `engaged` ↔ `thinking` ↔ `distracted` 之间跳跃 → 无法专注 → 困难度高。

状态切换次数归一化到 0~1 范围。

#### 3.3.3 fatigue_drift（平均疲劳）— 权重 0.20

窗口内疲劳分（fatigue_level）的平均值。越疲劳越难以学习。

#### 3.3.4 blank_stare（空白凝视）— 权重 0.15

检测「瞪着屏幕但不在学习」的状态。

**判定**：
1. 统计窗口内连续 `idle + screen` 的帧对数量
2. **如果窗口内存在任何 `writing` 或 `reading` 交互** → blank_stare = 0（说明在交替学习，不是发呆）
3. 如果完全没有任何书写/阅读交互 → blank_stare = 连续 idle_screen 占比

**关键区分**：
| 场景 | idle+screen 帧对 | 有 writing/reading | blank_stare |
|------|-----------------|-------------------|-------------|
| 认真听课 | 多 | ❌ 无 | **高** → 判断为发呆 |
| 听课+记笔记 | 多 | ✅ 有 | **0** → 正常交互式学习 |
| 看视频 | 多 | ❌ 无 | **高** → 可能是被动观看（争议） |

> 注意：blank_stare 对「纯听课/看视频」场景可能有误判，因为看视频时确实不会有 writing/reading。后续可引入「视频播放状态」外部信号来改善。当前版本中，纯听课场景的 blank_stare 会被 struggle_ratio（低）和 fatigue_drift（低）拉低总分，不会产生过高困难度。

#### 3.3.5 posture_decline（姿态坍塌趋势）— 权重 0.10

与旧版的 post_tilt（静态角度）不同，新版本检测的是 **姿态角度的递减趋势**：

1. 对窗口内所有躯干角度做线性回归
2. 负斜率 = 角度在减小 = 逐渐趴下
3. `posture_decline = max(0, min(-斜率/5.0, 1))` — 斜率 −5°/s 达到满分

**为什么用趋势而非绝对值？**
- 有些学生本身坐姿就前倾（正常学习姿态），静态角度偏低不代表困难
- 但如果一开始坐得很直，后来逐渐趴下去，说明在「崩溃」，这才是困难信号

### 3.4 输出

```
困难度 ∈ [0.0, 1.0]
```

| 分数区间 | 含义 |
|----------|------|
| 0.0~0.2 | 正常学习 |
| 0.2~0.4 | 轻微困难 |
| 0.4~0.6 | 中度困难，需要关注 |
| 0.6~0.8 | 严重困难，建议干预 |
| 0.8~1.0 | 极难，学生可能已放弃 |

---

## 四、每设备独立状态

所有涉及时间序列的状态（EAR历史、PERCLOS窗口、视线历史等）按 `device_id` 隔离存储。多设备并行时互不干扰。

```python
_device_states = {
    "watcher-AABBCCDD": {  # 设备1
        "ear_history": [...],
        "perclos_window": [...],
        "gaze_history": [...],
        ...
    },
    "watcher-EEFF0011": {  # 设备2
        ...
    },
}
```

---

## 五、参考文献

| 指标 | 文献 |
|------|------|
| EAR | Soukupová, T., & Čech, J. (2016). Real-Time Eye Blink Detection using Facial Landmarks. *CVWW 2016*. |
| PERCLOS | Wierwille, W. W., et al. (1999). *Research on Vehicle-Based Driver Status/Performance Monitoring*. FHWA-MC-99-133. |
| MAR (yawn) | Anitha, C., et al. (2020). Yawn Detection for Driver Drowsiness. *IJERT*, 9(2). |
| Head nod | Bergasa, L. M., et al. (2006). Real-time system for monitoring driver vigilance. *IEEE T-ITS*, 7(1). |
| Blink rate | Caffier, P. P., et al. (2003). The spontaneous eye-blink as a measure of sleepiness. *Psychophysiology*, 40(3). |
| FaceMesh | Kartynnik, Y., et al. (2019). Real-time Facial Surface Geometry from Monocular Video. *arXiv:1907.06724*. Google MediaPipe. |
| Pose | Bazarevsky, V., et al. (2020). BlazePose: On-device Real-time Body Pose Tracking. *arXiv:2006.10204*. Google MediaPipe. |

---

## 六、相关文件

| 文件 | 内容 |
|------|------|
| `analyzer.py` | 疲劳检测 + 学习状态分类实现 |
| `difficulty.py` | 困难度评估实现 |
| `models.py` | 数据库模型（含 learning_state 字段） |
| `tests/test_analyzer.py` | 单元测试 |
