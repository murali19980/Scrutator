"""Memory compression and archival utilities.

Automatically merges and prunes old memory entries to keep storage
size manageable while preserving important information.
"""

import logging
from typing import List
from memory.types import MemoryEntry

logger = logging.getLogger(__name__)


def compress_memories(entries: List[MemoryEntry], max_knowledge: int = 100) -> List[MemoryEntry]:
    """Compress memory entries by pruning oldest knowledge entries beyond the limit.

    Args:
        entries: Full list of memory entries.
        max_knowledge: Maximum number of knowledge entries to retain.

    Returns:
        Pruned list of memory entries.
    """
    if not entries:
        return []

    knowledge = [e for e in entries if e.type == "knowledge"]
    other = [e for e in entries if e.type != "knowledge"]

    if len(knowledge) <= max_knowledge:
        return entries

    # Sort by timestamp (oldest first) and keep only the most recent max_knowledge
    knowledge.sort(key=lambda e: e.timestamp if e.timestamp else e.timestamp)
    retained = knowledge[-max_knowledge:]
    pruned_count = len(knowledge) - max_knowledge

    logger.info(f"Compressed memory: removed {pruned_count} oldest knowledge entries, retained {max_knowledge}.")

    return other + retained
