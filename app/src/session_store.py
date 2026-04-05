"""Session store — Redis-backed with in-memory fallback."""
from __future__ import annotations
import json, logging, os
logger = logging.getLogger(__name__)

_redis = None
_memory: dict[str, dict] = {}

def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    url = os.environ.get("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis
        _redis = redis.from_url(url, decode_responses=True, socket_timeout=2)
        _redis.ping()
        logger.info("Redis session store connected")
    except Exception as e:
        logger.warning("Redis unavailable, using in-memory sessions: %s", e)
        _redis = None
    return _redis

SESSION_TTL = 4 * 3600  # 4 hours

def get_session(user_id: str) -> dict | None:
    r = _get_redis()
    if r:
        try:
            data = r.get(f"morgenruf:session:{user_id}")
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning("Redis get error: %s", e)
    return _memory.get(user_id)

def set_session(user_id: str, data: dict) -> None:
    r = _get_redis()
    if r:
        try:
            r.setex(f"morgenruf:session:{user_id}", SESSION_TTL, json.dumps(data))
            return
        except Exception as e:
            logger.warning("Redis set error: %s", e)
    _memory[user_id] = data

def delete_session(user_id: str) -> None:
    r = _get_redis()
    if r:
        try:
            r.delete(f"morgenruf:session:{user_id}")
        except Exception as e:
            logger.warning("Redis delete error: %s", e)
    _memory.pop(user_id, None)

def has_session(user_id: str) -> bool:
    return get_session(user_id) is not None
