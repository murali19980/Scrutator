"""Stop condition logic for research loop."""

from typing import Set

def should_stop(
    confidence: float,
    source_count: int,
    loop_count: int,
    max_loops: int,
    previous_urls: Set[str],
    current_urls: Set[str],
    confidence_threshold: float = 85.0,
    min_sources: int = 10,
    stop_early: bool = True
) -> bool:
    """
    Determine if research should stop.

    Args:
        confidence: Overall confidence score (0-100).
        source_count: Total number of unique sources gathered.
        loop_count: Current loop iteration.
        max_loops: Maximum allowed loops.
        previous_urls: Set of URLs from previous rounds.
        current_urls: Set of URLs from current round.
        confidence_threshold: Minimum confidence to stop.
        min_sources: Minimum number of sources required.
        stop_early: Whether to stop early when conditions are met.

    Returns:
        True if research should stop, False otherwise.
    """
    # Safety: max loops reached
    if loop_count >= max_loops:
        return True

    # Early stop: conditions met
    if stop_early and confidence >= confidence_threshold and source_count >= min_sources:
        return True

    # No new sources: if fewer than 3 new unique URLs found in this round
    # that were not already seen in prior rounds
    new_urls = current_urls - previous_urls
    if len(new_urls) < 3:
        return True

    # If confidence is very high, even if source count is slightly low
    if confidence >= 95 and source_count >= 5:
        return True

    return False
