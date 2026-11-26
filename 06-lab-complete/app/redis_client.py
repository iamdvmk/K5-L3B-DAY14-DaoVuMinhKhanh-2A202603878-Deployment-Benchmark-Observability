"""Kết nối Redis dùng chung cho rate limiter và cost guard."""
import redis

from app.config import settings

# from_url KHÔNG mở kết nối ngay → app vẫn khởi động được khi Redis chưa sẵn sàng
r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


def redis_healthy() -> bool:
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False