"""
Progress feedback system for real-time updates and cancellation.

This module provides:
- Progress tracking with callbacks
- Cancellation support
- Thread-safe updates
"""

import asyncio
import logging
from typing import Callable, Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

@dataclass
class ProgressUpdate:
    """A progress update message."""
    step: str
    message: str
    progress: float  # 0.0 to 1.0
    timestamp: datetime = field(default_factory=datetime.now)
    details: Optional[Dict[str, Any]] = None
    task_id: Optional[str] = None


class ProgressTracker:
    """
    Thread-safe progress tracker with cancellation support.
    
    Features:
    - Add/remove callbacks
    - Update progress
    - Cancel tasks
    - Check cancellation state
    """
    
    def __init__(self, task_id: Optional[str] = None):
        self.task_id = task_id or str(uuid.uuid4())
        self.callbacks: List[Callable[[ProgressUpdate], None]] = []
        self._cancelled = False
        self._completed = False
        self._lock = asyncio.Lock()
        self.current_step = ""
        self.current_progress = 0.0
        self._logs: List[str] = []
        self._max_logs = 100
    
    def add_callback(self, callback: Callable[[ProgressUpdate], None]) -> None:
        """Add a callback to receive progress updates."""
        if callback not in self.callbacks:
            self.callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[ProgressUpdate], None]) -> None:
        """Remove a callback."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    async def update(
        self,
        step: str,
        message: str,
        progress: float,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Send a progress update to all callbacks.
        
        Args:
            step: Current step name (e.g., "searching", "scoring")
            message: Human-readable message
            progress: Progress value (0.0 to 1.0)
            details: Optional additional details
        """
        if self._cancelled:
            return
        
        self.current_step = step
        self.current_progress = min(max(progress, 0.0), 1.0)
        self._logs.append(f"[{step}] {message}")
        if len(self._logs) > self._max_logs:
            self._logs.pop(0)
        
        update = ProgressUpdate(
            step=step,
            message=message,
            progress=self.current_progress,
            details=details or {},
            task_id=self.task_id
        )
        
        async with self._lock:
            for cb in self.callbacks:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(update)
                    else:
                        cb(update)
                except Exception as e:
                    logger.warning(f"Progress callback error: {e}")
    
    def cancel(self) -> None:
        """Cancel the current task."""
        self._cancelled = True
        logger.info(f"Task {self.task_id} cancelled")
    
    def is_cancelled(self) -> bool:
        """Check if the task has been cancelled."""
        return self._cancelled
    
    def complete(self) -> None:
        """Mark the task as completed."""
        self._completed = True
    
    def is_completed(self) -> bool:
        """Check if the task has been completed."""
        return self._completed
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status."""
        return {
            "task_id": self.task_id,
            "cancelled": self._cancelled,
            "completed": self._completed,
            "current_step": self.current_step,
            "progress": self.current_progress,
            "logs": self._logs[-10:]  # Last 10 logs
        }
    
    def get_logs(self, limit: int = 20) -> List[str]:
        """Get recent logs."""
        return self._logs[-limit:]
