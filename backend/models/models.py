import json
from sqlalchemy import Column, String, Float, Integer, Text, DateTime, Index, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_published_at", "published_at"),
    )

    id = Column(String, primary_key=True)
    title = Column(String)
    url = Column(String, unique=True, index=True)
    source = Column(String)
    published_at = Column(String)
    content_snippet = Column(String)
    fetched_at = Column(String)
    sectors = Column(Text, nullable=True)  # JSON-serialized list of source-assigned sectors
    cluster_id = Column(String, nullable=True)
    embedding = Column(Text, nullable=True)  # JSON-serialized list of floats
    image_url = Column(String, nullable=True)  # Extracted from RSS media/thumbnail tags


class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(String, primary_key=True)
    theme = Column(String)


class Summary(Base):
    __tablename__ = "stories"
    __table_args__ = (
        Index("ix_stories_relevance_score", "relevance_score"),
        Index("ix_stories_gs_paper", "gs_paper"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String)
    summary = Column(String)
    why_it_matters = Column(String)
    url = Column(String, nullable=True)
    score = Column(Float)
    article_count = Column(Integer)
    source = Column(String)
    published_at = Column(String)
    latest_at = Column(String)
    created_at = Column(String)
    sectors = Column(String)  # JSON-serialized list
    sector_summary = Column(Text, nullable=True)  # Per-sector summary
    trending_score = Column(Float, nullable=True)  # Historical trending
    image_url = Column(String, nullable=True)  # Image from the cluster's best article

    # --- Source Metadata Columns ---
    source_type = Column(String, nullable=True)        # Type: government, legislative, explainer, editorial, environment, news
    authority_score = Column(Float, nullable=True)     # Source authority score (0-1)
    content_type = Column(String, nullable=True)       # Detected content type: editorial, explainer, policy_release, bill, etc.
    source_priority = Column(String, nullable=True)    # Priority: very_high, high, medium, low

    # --- UPSC Exam Intelligence Columns ---
    relevance_score = Column(Float, nullable=True)  # UPSC relevance score (0-1)
    priority_score = Column(Float, nullable=True)  # Priority score (0-1)
    novelty_score = Column(Float, nullable=True)   # Novelty score (0-1)
    gs_paper = Column(String, nullable=True)       # GS paper mapping (e.g., "GS2", "GS3", "Prelims")
    subtopics = Column(Text, nullable=True)         # JSON-serialized list of subtopics
    exam_playbook = Column(Text, nullable=True)     # JSON-serialized exam intelligence from OpenRouter/Owl Alpha
    ai_review = Column(Text, nullable=True)          # JSON-serialized AI review verdict (PASS/FLAG/REJECT)
    ml_prediction = Column(Text, nullable=True)      # JSON-serialized ML prediction (verdict, confidence, probabilities)


class StoryReview(Base):
    __tablename__ = "story_reviews"

    id = Column(String, primary_key=True, index=True)
    story_title = Column(String, nullable=False)
    story_url = Column(String, nullable=True)

    # Core review fields
    is_relevant = Column(String, nullable=False)           # "yes" / "no" — is this story relevant to UPSC?
    sector_correct = Column(String, nullable=False)        # "yes" / "no" — is the sector mapping correct?
    suggested_sector = Column(String, nullable=True)       # If sector wrong, correct sector
    gs_paper_correct = Column(String, nullable=False)      # "yes" / "no" — is the GS paper mapping correct?
    suggested_gs_paper = Column(String, nullable=True)     # If paper wrong, correct paper
    suggestions = Column(Text, nullable=True)              # Free-text suggestions

    # Legacy fields (kept for backward compat)
    correct_section = Column(String, nullable=True)
    suggested_section = Column(String, nullable=True)
    summary_concise = Column(String, nullable=True)
    picture_available = Column(String, nullable=True)
    comment = Column(Text, nullable=True)

    created_at = Column(String, nullable=False)
