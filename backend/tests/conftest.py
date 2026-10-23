"""Pytest configuration and shared fixtures."""
import sys
import os
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment before imports
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("STORAGE_ROOT", "/tmp/sih_test_storage")
