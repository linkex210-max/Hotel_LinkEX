from django.core.cache import cache


def is_rate_limited(request, scope: str, limit: int = 60, window_seconds: int = 60) -> bool:
    """
    محدد معدل الطلبات (Rate Limiter) يعتمد على Django Cache (Redis في الإنتاج).
    """
    ip = (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR", "unknown")
    )
    key = f"rl:{scope}:{ip}"
    count = cache.get(key)
    if count is None:
        cache.set(key, 1, timeout=window_seconds)
        return False
    if count >= limit:
        return True
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
    return False
