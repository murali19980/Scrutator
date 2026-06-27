"""
Unit tests for progress tracking and cancellation.
"""

import pytest
import asyncio
from core.feedback import ProgressTracker, ProgressUpdate


@pytest.mark.asyncio
async def test_progress_updates():
    """Test that progress updates are sent to callbacks."""
    updates = []
    
    def callback(update):
        updates.append(update)
    
    tracker = ProgressTracker()
    tracker.add_callback(callback)
    
    await tracker.update("test", "Test message", 0.5)
    
    assert len(updates) == 1
    assert updates[0].step == "test"
    assert updates[0].message == "Test message"
    assert updates[0].progress == 0.5


@pytest.mark.asyncio
async def test_cancellation():
    """Test that cancellation is properly tracked."""
    tracker = ProgressTracker()
    assert not tracker.is_cancelled()
    tracker.cancel()
    assert tracker.is_cancelled()


@pytest.mark.asyncio
async def test_multiple_callbacks():
    """Test that multiple callbacks receive updates."""
    updates1 = []
    updates2 = []
    
    def cb1(update):
        updates1.append(update)
    
    def cb2(update):
        updates2.append(update)
    
    tracker = ProgressTracker()
    tracker.add_callback(cb1)
    tracker.add_callback(cb2)
    
    await tracker.update("test", "Message", 0.5)
    
    assert len(updates1) == 1
    assert len(updates2) == 1


@pytest.mark.asyncio
async def test_callback_exception_handling():
    """Test that exceptions in callbacks don't break the tracker."""
    def bad_callback(update):
        raise ValueError("Test error")
    
    tracker = ProgressTracker()
    tracker.add_callback(bad_callback)
    
    # Should not raise
    await tracker.update("test", "Message", 0.5)
    assert tracker.get_status()["progress"] == 0.5


@pytest.mark.asyncio
async def test_progress_bounds():
    """Test that progress values are clamped between 0 and 1."""
    tracker = ProgressTracker()
    updates = []
    
    def callback(update):
        updates.append(update)
    
    tracker.add_callback(callback)
    
    await tracker.update("test", "Below", -0.5)
    assert updates[-1].progress == 0.0
    
    await tracker.update("test", "Above", 1.5)
    assert updates[-1].progress == 1.0


@pytest.mark.asyncio
async def test_log_limit():
    """Test that logs are limited to max_logs."""
    tracker = ProgressTracker()
    tracker._max_logs = 3
    
    for i in range(5):
        await tracker.update(f"step_{i}", f"Message {i}", i/5)
    
    logs = tracker.get_logs()
    assert len(logs) == 3
    assert "Message 2" in logs[0]
    assert "Message 4" in logs[-1]


@pytest.mark.asyncio
async def test_status():
    """Test that status returns correct information."""
    tracker = ProgressTracker()
    await tracker.update("test_step", "Test message", 0.7)
    
    status = tracker.get_status()
    assert status["current_step"] == "test_step"
    assert status["progress"] == 0.7
    assert not status["cancelled"]
    assert not status["completed"]
