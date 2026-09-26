"""
SOCMIntelligence - tek komutla baslatma noktasi.

    pip install -r requirements.txt
    uvicorn server:app --host 0.0.0.0 --port 8000

Tarayicida: http://localhost:8000/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.main import app  # noqa: E402,F401
