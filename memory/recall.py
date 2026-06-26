"""Retrieve relevant memories matching search criteria."""

import logging
from typing import List
from memory.manager import MemoryManager
from memory.types import MemoryEntry

logger = logging.getLogger(__name__)

def recall_relevant_memories(
    manager: MemoryManager,
    query: str,
    threshold: float = 0.4
) -> List[MemoryEntry]:
    """
    Search and retrieve relevant preference, feedback, or knowledge memories.
    """
    if not manager:
        return []
    try:
        memories = manager.find(query, threshold=threshold)
        logger.info(f"Recalled {len(memories)} relevant memories for query: {query}")
        return memories
    except Exception as e:
        logger.error(f"Recall failed: {e}")
        return []
