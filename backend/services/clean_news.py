import re
import logging

logger = logging.getLogger(__name__)

def clean_text(text: str) -> str:
    """Basic text cleaning."""
    if not text:
        return ""
    # Strip HTML tags
    text = re.sub(r"<[^>]*>", "", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text

def clean_articles(articles: list[dict]) -> list[dict]:
    """Clean title and content of articles."""
    for a in articles:
        a["title"] = clean_text(a.get("title", ""))
        a["content_snippet"] = clean_text(a.get("content_snippet", ""))
    return articles
