"""JSON I/O storage for local memory store."""

import json
import os
import logging
from typing import List, Dict
from memory.types import MemoryEntry

logger = logging.getLogger(__name__)

class JSONStorage:
    def __init__(self, file_path: str = "./memory_store.json"):
        self.file_path = file_path

    def load(self) -> List[MemoryEntry]:
        """Load memory entries from JSON file."""
        if not os.path.exists(self.file_path):
            logger.info(f"Memory store file {self.file_path} not found. Starting with empty memory.")
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = []
            for item in data:
                try:
                    entries.append(MemoryEntry.from_dict(item))
                except Exception as e:
                    logger.warning(f"Failed to parse memory entry: {item}. Error: {e}")
            logger.info(f"Loaded {len(entries)} memory entries from {self.file_path}.")
            return entries
        except Exception as e:
            logger.error(f"Failed to load memory store from {self.file_path}: {e}")
            return []

    def save(self, entries: List[MemoryEntry]):
        """Save memory entries to JSON file."""
        try:
            # Ensure parent directories exist
            dir_name = os.path.dirname(self.file_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
                
            data = [entry.to_dict() for entry in entries]
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(entries)} memory entries to {self.file_path}.")
        except Exception as e:
            logger.error(f"Failed to save memory store to {self.file_path}: {e}")
