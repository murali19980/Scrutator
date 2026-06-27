"""JSON I/O storage for local memory store with HMAC integrity protection."""

import hashlib
import hmac
import json
import logging
import os
import warnings
from typing import List
from memory.types import MemoryEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HMAC helpers
# ---------------------------------------------------------------------------

def _get_hmac_secret() -> bytes:
    """Return the HMAC signing key from env or Docker secret, with a loud fallback."""
    # 1. Docker secret
    secret_path = "/run/secrets/memory_hmac_key"
    if os.path.exists(secret_path):
        try:
            with open(secret_path) as f:
                secret = f.read().strip()
            if secret:
                return secret.encode()
        except OSError:
            pass

    # 2. Environment variable
    secret = os.environ.get("SCRUTATOR_MEMORY_HMAC_KEY", "")
    if not secret:
        warnings.warn(
            "SCRUTATOR_MEMORY_HMAC_KEY is not set. "
            "Memory integrity checking is weakened. "
            "Set this variable in your .env or Docker secrets.",
            stacklevel=3,
        )
        secret = "default-insecure-fallback-set-this-in-env"
    return secret.encode()


def _sign(payload: bytes) -> str:
    return hmac.new(_get_hmac_secret(), payload, hashlib.sha256).hexdigest()


def _verify(payload: bytes, signature: str) -> bool:
    expected = _sign(payload)
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# JSONStorage
# ---------------------------------------------------------------------------

class JSONStorage:
    def __init__(self, file_path: str = "./memory_store.json"):
        self.file_path = file_path

    def load(self) -> List[MemoryEntry]:
        """Load memory entries from JSON file, verifying HMAC integrity."""
        if not os.path.exists(self.file_path):
            logger.info(
                f"Memory store file {self.file_path} not found. Starting with empty memory."
            )
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                envelope = json.load(f)

            # Support both old format (plain list) and new signed format
            if isinstance(envelope, list):
                # Legacy plain list — load without signature check, will be signed on next save
                logger.warning(
                    "Memory store is in legacy unsigned format. "
                    "It will be re-signed on next save."
                )
                raw_entries = envelope
            elif isinstance(envelope, dict) and "data" in envelope:
                # New signed format — verify integrity
                payload = json.dumps(
                    envelope["data"], sort_keys=True, ensure_ascii=False
                ).encode()
                if not _verify(payload, envelope.get("sig", "")):
                    raise ValueError(
                        f"Memory file integrity check failed: {self.file_path}. "
                        "The file may have been tampered with."
                    )
                raw_entries = envelope["data"]
            else:
                logger.error(f"Unrecognised memory file format at {self.file_path}")
                return []

            entries = []
            for item in raw_entries:
                try:
                    entries.append(MemoryEntry.from_dict(item))
                except Exception as e:
                    logger.warning(f"Failed to parse memory entry: {item}. Error: {e}")
            logger.info(f"Loaded {len(entries)} memory entries from {self.file_path}.")
            return entries

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to load memory store from {self.file_path}: {e}")
            return []

    def save(self, entries: List[MemoryEntry]) -> None:
        """Save memory entries to JSON file with HMAC signature and chmod 600."""
        try:
            dir_name = os.path.dirname(self.file_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            raw_data = [entry.to_dict() for entry in entries]
            payload = json.dumps(raw_data, sort_keys=True, ensure_ascii=False).encode()
            envelope = {
                "data": raw_data,
                "sig": _sign(payload),
            }

            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(envelope, f, indent=2, ensure_ascii=False)

            # Restrict file permissions to owner-only read/write
            try:
                os.chmod(self.file_path, 0o600)
            except OSError:
                # chmod is a no-op on Windows — that's acceptable
                pass

            logger.info(f"Saved {len(entries)} memory entries to {self.file_path}.")
        except Exception as e:
            logger.error(f"Failed to save memory store to {self.file_path}: {e}")
