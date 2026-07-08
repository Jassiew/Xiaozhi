import os
import secrets

# 服务器
WS_PORT = int(os.getenv("WS_PORT", "8000"))
API_PORT = int(os.getenv("API_PORT", "8000"))

# MySQL
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root")
MYSQL_DB = os.getenv("MYSQL_DB", "student_monitor")

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24  # 24小时

# 帧处理
FRAME_SAVE_DIR = os.getenv("FRAME_SAVE_DIR", "./frames")
QUEUE_MAXSIZE = 50

# 每个学习时段最长分钟数，超时自动结束并开启新时段
SESSION_MAX_MINUTES = int(os.getenv("SESSION_MAX_MINUTES", "10"))

# 人离开画面超过此秒数后自动结束当前学习时段，回来后开启新时段
ABSENCE_GRACE_S = int(os.getenv("ABSENCE_GRACE_S", "15"))

# 隐私：是否保存所有帧图片（默认 false，仅保存异常告警帧）
SAVE_ALL_FRAMES = os.getenv("SAVE_ALL_FRAMES", "false").lower() == "true"

# AES-128 加密密钥（16字节），与小智端固件 crypto_utils.cc 中保持一致
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "xiaozhi-watcher1")

# 数据保留天数，超期自动清理帧图片和数据库记录
FRAME_RETENTION_DAYS = int(os.getenv("FRAME_RETENTION_DAYS", "7"))

# 初始化管理员账号（首次启动用）
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
