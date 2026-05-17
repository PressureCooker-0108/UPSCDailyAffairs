import json
from sqlalchemy import Column, String, Float, Integer, Text, DateTime, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Article(Base):
    __tablename__ = "articles"

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


class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, index=True)
    name = Column(String)
    price = Column(Float)
    change = Column(Float)
    change_pct = Column(Float)
    market_cap = Column(String, nullable=True)
    sector = Column(String)
    recorded_at = Column(String)


class Briefing(Base):
    __tablename__ = "briefings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text)  # Markdown briefing text
    created_at = Column(String)


class SectorSummary(Base):
    __tablename__ = "sector_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sector = Column(String, index=True)
    summary = Column(Text)
    headline_count = Column(Integer)
    created_at = Column(String)


class StoryReview(Base):
    __tablename__ = "story_reviews"

    id = Column(String, primary_key=True, index=True)
    story_title = Column(String, nullable=False)
    story_url = Column(String, nullable=True)
    correct_section = Column(String, nullable=False)
    suggested_section = Column(String, nullable=True)
    summary_concise = Column(String, nullable=False)
    picture_available = Column(String, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(String, nullable=False)
