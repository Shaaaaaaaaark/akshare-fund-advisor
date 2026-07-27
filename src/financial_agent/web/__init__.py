"""Static web interface bundled with the API package."""

from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent

__all__ = ["WEB_ROOT"]
