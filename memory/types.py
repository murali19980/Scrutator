from dataclasses import dataclass, field
from typing import Literal, Dict, Optional
from datetime import datetime

@dataclass
class MemoryEntry:
    id: str
    topic: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    confidence: float = 0.0
    metadata: Dict = field(default_factory=dict)
    type: Literal["knowledge", "preference", "feedback"] = "knowledge"

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.type,
            "topic": self.topic,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'MemoryEntry':
        t_str = data.get("timestamp")
        try:
            timestamp = datetime.fromisoformat(t_str) if t_str else datetime.now()
        except:
            timestamp = datetime.now()

        entry_type = data.get("type", "knowledge")
        if entry_type == "knowledge":
            return KnowledgeMemory(
                id=data["id"],
                topic=data["topic"],
                content=data["content"],
                timestamp=timestamp,
                confidence=data.get("confidence", 0.0),
                metadata=data.get("metadata", {})
            )
        elif entry_type == "preference":
            return PreferenceMemory(
                id=data["id"],
                topic=data["topic"],
                content=data["content"],
                timestamp=timestamp,
                confidence=data.get("confidence", 0.0),
                metadata=data.get("metadata", {})
            )
        elif entry_type == "feedback":
            return FeedbackMemory(
                id=data["id"],
                topic=data["topic"],
                content=data["content"],
                timestamp=timestamp,
                confidence=data.get("confidence", 0.0),
                metadata=data.get("metadata", {})
            )
        else:
            return cls(
                id=data["id"],
                topic=data["topic"],
                content=data["content"],
                timestamp=timestamp,
                confidence=data.get("confidence", 0.0),
                metadata=data.get("metadata", {}),
                type=entry_type
            )

@dataclass
class KnowledgeMemory(MemoryEntry):
    def __post_init__(self):
        self.type = "knowledge"

@dataclass
class PreferenceMemory(MemoryEntry):
    def __post_init__(self):
        self.type = "preference"

@dataclass
class FeedbackMemory(MemoryEntry):
    def __post_init__(self):
        self.type = "feedback"
