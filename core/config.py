"""Configuration helper for Scrutator."""

import os
from pathlib import Path

def get_config_path(filename: str = "settings.yaml") -> Path:
    """Get absolute path to config file relative to project root."""
    project_root = Path(__file__).parent.parent
    return project_root / "config" / filename
