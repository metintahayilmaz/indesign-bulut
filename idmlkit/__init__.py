"""idmlkit — InDesign IDML belgelerini metin düzeyinde okuma ve düzenleme araçları."""
from .document import IdmlDocument
from .text import Paragraph

__all__ = ["IdmlDocument", "Paragraph"]
