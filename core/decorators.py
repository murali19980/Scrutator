"""
Decorators for retry logic and error handling.
"""

import asyncio
import logging
import random
from functools import wraps
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exponential: bool = True,
    jitter: bool = True,
    retry_exceptions: tuple = (Exception,)
):
    """
    Decorator for retrying asynchronous functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds between retries.
        exponential: Whether to use exponential backoff.
        jitter: Whether to add random jitter to delays.
        retry_exceptions: Tuple of exceptions to retry on.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        # Calculate delay
                        if exponential:
                            delay = base_delay * (2 ** (attempt - 1))
                        else:
                            delay = base_delay
                        if jitter:
                            delay += random.uniform(0, 0.5)
                        await asyncio.sleep(delay)
                    return await func(*args, **kwargs)
                except retry_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Retry {attempt+1}/{max_retries} for {func.__name__}: {e}"
                        )
                    else:
                        logger.error(f"All retries failed for {func.__name__}: {e}")
                        raise
            raise last_exception
        return wrapper
    return decorator


def handle_errors(error_type: str = "UNKNOWN"):
    """
    Decorator to catch and format errors for user-friendly output.
    
    Args:
        error_type: The error type to use for formatting.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}")
                from core.errors import ErrorFormatter
                raise ValueError(ErrorFormatter.format_exception(e))
        return wrapper
    return decorator
