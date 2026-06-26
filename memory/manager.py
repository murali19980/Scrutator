"""Memory Manager for Scrutator."""

import logging
import os
from typing import List, Dict, Optional
from datetime import datetime
import re

from memory.types import MemoryEntry, KnowledgeMemory, PreferenceMemory, FeedbackMemory
from memory.storage import JSONStorage

logger = logging.getLogger(__name__)

# Try to import ChromaDB and SentenceTransformers
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("ChromaDB or SentenceTransformers not available. Falling back to JSON search.")

class MemoryManager:
    def __init__(self, config: Dict):
        self.config = config
        self.storage_type = config.get("storage_type", "json")
        self.storage_path = config.get("storage_path", "./memory_store.json")
        
        # Always initialize JSON Storage as secondary/backup
        self.json_storage = JSONStorage(self.storage_path)
        self.entries = self.json_storage.load()
        
        # ChromaDB setup
        self.chroma_client = None
        self.chroma_collection = None
        self.embedding_model = None

        if self.storage_type == "chromadb" and CHROMA_AVAILABLE:
            try:
                persist_dir = config.get("persist_dir", "./chroma_db")
                os.makedirs(persist_dir, exist_ok=True)
                self.chroma_client = chromadb.PersistentClient(path=persist_dir)
                
                collection_name = config.get("collection_name", "scrutator_memory")
                self.chroma_collection = self.chroma_client.get_or_create_collection(name=collection_name)
                
                model_name = config.get("embedding_model", "all-MiniLM-L6-v2")
                logger.info(f"Loading embedding model: {model_name}...")
                self.embedding_model = SentenceTransformer(model_name)
                
                # Sync JSON entries into ChromaDB if Chroma is empty
                if self.chroma_collection.count() == 0 and self.entries:
                    logger.info("Syncing JSON memories to ChromaDB...")
                    self._sync_to_chroma(self.entries)
                    
            except Exception as e:
                logger.error(f"ChromaDB initialization failed: {e}. Falling back to JSON storage.")
                self.storage_type = "json"

    def _sync_to_chroma(self, entries: List[MemoryEntry]):
        """Helper to batch add entries to ChromaDB."""
        if not self.chroma_collection or not self.embedding_model:
            return
        
        ids = [e.id for e in entries]
        documents = [e.content for e in entries]
        embeddings = self.embedding_model.encode(documents).tolist()
        metadatas = []
        for e in entries:
            meta = e.metadata.copy()
            meta.update({
                "type": e.type,
                "topic": e.topic,
                "timestamp": e.timestamp.isoformat(),
                "confidence": e.confidence
            })
            metadatas.append(meta)
            
        self.chroma_collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

    def add(self, entry: MemoryEntry):
        """Add a memory entry."""
        # 1. Add to local list and save to JSON
        self.entries.append(entry)
        self.json_storage.save(self.entries)
        
        # 2. Add to ChromaDB if active
        if self.storage_type == "chromadb" and self.chroma_collection and self.embedding_model:
            try:
                embedding = self.embedding_model.encode([entry.content]).tolist()
                meta = entry.metadata.copy()
                meta.update({
                    "type": entry.type,
                    "topic": entry.topic,
                    "timestamp": entry.timestamp.isoformat(),
                    "confidence": entry.confidence
                })
                self.chroma_collection.add(
                    ids=[entry.id],
                    embeddings=embedding,
                    documents=[entry.content],
                    metadatas=[meta]
                )
                logger.info(f"Memory added to ChromaDB: {entry.id}")
            except Exception as e:
                logger.error(f"Failed to add memory to ChromaDB: {e}")

    def find(self, topic: str, threshold: float = 0.3) -> List[MemoryEntry]:
        """Find memories matching a topic or search term."""
        if self.storage_type == "chromadb" and self.chroma_collection and self.embedding_model:
            try:
                query_vector = self.embedding_model.encode([topic]).tolist()
                results = self.chroma_collection.query(
                    query_embeddings=query_vector,
                    n_results=5
                )
                
                matched_entries = []
                if results and results.get("ids") and results["ids"][0]:
                    ids = results["ids"][0]
                    distances = results["distances"][0] if results.get("distances") else [0]*len(ids)
                    
                    for idx, doc_id in enumerate(ids):
                        # Distance check (Chroma returns cosine distance or L2.
                        # For cosine, distance is 1 - similarity. So similarity = 1 - distance)
                        similarity = 1.0 - distances[idx]
                        if similarity >= threshold:
                            # Retrieve entry from self.entries
                            for entry in self.entries:
                                if entry.id == doc_id:
                                    matched_entries.append(entry)
                                    break
                                    
                return matched_entries
            except Exception as e:
                logger.error(f"ChromaDB query failed: {e}. Falling back to keyword matching.")

        # Fallback keyword matching (simple overlap coefficient)
        topic_words = set(re.findall(r'\w+', topic.lower()))
        matched = []
        for entry in self.entries:
            entry_words = set(re.findall(r'\w+', (entry.topic + " " + entry.content).lower()))
            intersection = topic_words.intersection(entry_words)
            if intersection:
                score = len(intersection) / min(len(topic_words), len(entry_words))
                if score >= threshold:
                    matched.append((entry, score))
                    
        # Sort by score descending
        matched.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in matched[:5]]

    def get_by_type(self, type_name: str) -> List[MemoryEntry]:
        """Get all memories of a specific type."""
        return [e for e in self.entries if e.type == type_name]

    def compress(self):
        """
        Merge / compress old memories of the same topic to reduce size.
        For MVP, we just do a timestamp-based prune or log it.
        """
        logger.info("Executing memory compression...")
        # Summarize older knowledge entries if they grow too large
        # We keep the code simple: limit knowledge items to 100, removing oldest
        knowledge_entries = self.get_by_type("knowledge")
        if len(knowledge_entries) > 100:
            knowledge_entries.sort(key=lambda x: x.timestamp)
            to_remove = len(knowledge_entries) - 100
            ids_to_remove = [e.id for e in knowledge_entries[:to_remove]]
            
            self.entries = [e for e in self.entries if e.id not in ids_to_remove]
            self.json_storage.save(self.entries)
            
            if self.storage_type == "chromadb" and self.chroma_collection:
                try:
                    self.chroma_collection.delete(ids=ids_to_remove)
                except Exception as e:
                    logger.error(f"Failed to delete compressed items from ChromaDB: {e}")
            logger.info(f"Compressed memory by removing {to_remove} oldest knowledge entries.")
