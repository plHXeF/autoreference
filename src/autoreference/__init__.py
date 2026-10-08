"""AutoReference public package."""

from .config import Settings
from .models import CitationAssessment, ReferenceCandidate, SearchResult
from .service import SearchService

__all__ = [
    "CitationAssessment",
    "ReferenceCandidate",
    "SearchResult",
    "SearchService",
    "Settings",
]

__version__ = "0.2.0a0"
