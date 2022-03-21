import logging
import time
from functools import wraps
from typing import Optional

logger = logging.getLogger()


def retry(base=2, count=1):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwds):
            exc: Optional[Exception] = None
            attempts = count
            while attempts:
                try:
                    return f(*args, **kwds)
                except Exception as e:
                    exc = e
                    if attempts:
                        delay = base ** (count - attempts + 1)
                        logger.info(
                            "Retrying %s for %s more times, sleeping for %s...",
                            getattr(f, "__name__"),
                            str(attempts),
                            delay,
                        )
                        time.sleep(delay)
                        attempts -= 1
            if exc:
                raise exc

        return wrapper

    return decorator
