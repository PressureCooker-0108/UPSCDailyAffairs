import logging
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from config import TOPIC_TEMPLATES

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Rich topic descriptions for TF-IDF-based "Why It Matters"
# These are keyword-dense descriptions that work well with TF-IDF
# for matching story content to the most relevant context template.
# ──────────────────────────────────────────────
_TOPIC_DESCRIPTIONS = {
    "election": (
        "Elections, political campaigns, voting, and transitions of power. "
        "Changes in government leadership that affect policy direction, "
        "market sentiment, and international relations."
    ),
    "war": (
        "Armed conflicts, military operations, wars, and invasions. "
        "Geopolitical instability that disrupts global supply chains, "
        "affects energy prices, and creates humanitarian crises."
    ),
    "economy": (
        "Economic indicators, GDP growth, inflation, unemployment, "
        "recessions, and fiscal policy. Broad economic shifts that "
        "impact business investment, consumer spending, and markets."
    ),
    "fed": (
        "Central bank policy, Federal Reserve decisions, interest rate "
        "changes, and monetary policy directly influencing borrowing costs "
        "and capital flows."
    ),
    "rate": (
        "Interest rate decisions by central banks, bond yields, "
        "and borrowing costs. Rate changes ripple through mortgages, "
        "business loans, corporate financing, and currency markets."
    ),
    "ai": (
        "Artificial intelligence, machine learning, automation, and "
        "advanced computing. AI breakthroughs are reshaping industries, "
        "labor markets, productivity, and competitive dynamics worldwide."
    ),
    "climate": (
        "Climate change, extreme weather events, environmental policy, "
        "and natural disasters. Climate developments affect agriculture, "
        "insurance, infrastructure, energy policy, and supply chains."
    ),
    "market": (
        "Stock market movements, trading, investor sentiment, and "
        "market volatility. Market movements reflect investor confidence "
        "and can signal broader economic trends and risks."
    ),
    "health": (
        "Public health crises, disease outbreaks, healthcare policy, "
        "and medical breakthroughs. Health issues affect workforce "
        "productivity, government spending, and global supply chains."
    ),
    "trade": (
        "International trade, tariffs, trade wars, and trade agreements. "
        "Trade policy changes directly affect prices, employment, "
        "manufacturing, and international relations."
    ),
}


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

# ── Pre-fit TF-IDF on rich topic descriptions for "Why It Matters" ──
_topic_names = list(_TOPIC_DESCRIPTIONS.keys())
_topic_texts = [_TOPIC_DESCRIPTIONS[k] for k in _topic_names]

_tfidf_vectorizer = TfidfVectorizer(
    max_features=500,
    stop_words="english",
    sublinear_tf=True,
    use_idf=False,
)
_topic_vectors = _tfidf_vectorizer.fit_transform(_topic_texts).toarray()
# Normalize topic vectors
_topic_norms = np.linalg.norm(_topic_vectors, axis=1, keepdims=True) + 1e-9
_topic_vectors = _topic_vectors / _topic_norms


def _pick_headline(cluster: list[dict]) -> tuple[str, str]:
    """
    Pick the best headline from a cluster.
    Uses TF-IDF centroid-based selection: finds the title closest to the centroid.
    Also prefers titles that are informative (longer, more substantive) as a tiebreaker.
    """
    if len(cluster) == 1:
        return cluster[0]["title"], cluster[0]["url"]
    try:
        titles = [a["title"] for a in cluster]
        vectorizer = TfidfVectorizer(stop_words="english", max_features=200, sublinear_tf=True)
        vectors = vectorizer.fit_transform(titles).toarray()

        # Normalize
        norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
        vectors = vectors / norms

        centroid = np.mean(vectors, axis=0)
        centroid_norm = np.linalg.norm(centroid) + 1e-9
        centroid = centroid / centroid_norm

        sims = vectors @ centroid

        # Prefer more informative titles (longer, more substantive) when similarity is close
        # Weight: 80% similarity, 20% title informativeness (length normalized)
        title_lengths = np.array([max(len(t.split()), 3) for t in titles])
        max_len = title_lengths.max()
        length_scores = title_lengths / max_len if max_len > 0 else np.ones_like(title_lengths)

        combined_scores = 0.8 * sims + 0.2 * length_scores
        best_idx = int(np.argmax(combined_scores))
        return titles[best_idx], cluster[best_idx]["url"]
    except Exception:
        return cluster[0]["title"], cluster[0]["url"]


def _make_summary(cluster: list[dict]) -> str:
    """
    Extractive summarization using embeddings.
    
    Collects all snippets from the cluster, splits them into sentences,
    embeds each sentence, and selects the most information-rich and
    representative sentences (closest to the semantic centroid).
    This produces a coherent multi-sentence summary that captures the
    key angles of the story.
    """
    snippets = [a.get("content_snippet", "") for a in cluster if a.get("content_snippet")]
    if not snippets:
        return "Details are still emerging."

    # Extract all sentences from all snippets
    all_sentences = []
    for snippet in snippets:
        snippet_sentences = _SENTENCE_RE.split(snippet)
        for s in snippet_sentences:
            s = s.strip()
            # Filter out very short fragments and boilerplate
            if len(s) > 30 and not s.startswith("<") and len(s.split()) >= 4:
                all_sentences.append(s)

    if not all_sentences:
        # Fallback: just use the first snippet as-is
        combined = snippets[0].strip()
        sentences = _SENTENCE_RE.split(combined)
        summary = ". ".join(s.strip() for s in sentences[:2] if s.strip())
        if summary and not summary.endswith("."):
            summary += "."
        return summary or "Details are still emerging."

    # Deduplicate near-identical sentences
    unique_sentences = []
    seen = set()
    for s in all_sentences:
        key = s.lower()[:60]
        if key not in seen:
            seen.add(key)
            unique_sentences.append(s)

    if len(unique_sentences) <= 2:
        return " ".join(unique_sentences) + ("." if not unique_sentences[-1].endswith(".") else "")

    try:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=300, sublinear_tf=True)
        sent_vecs = vectorizer.fit_transform(unique_sentences).toarray()

        # Normalize for cosine similarity
        norms = np.linalg.norm(sent_vecs, axis=1, keepdims=True) + 1e-9
        sent_vecs = sent_vecs / norms

        # Centroid: the "average" TF-IDF vector of all sentences
        centroid = np.mean(sent_vecs, axis=0)
        centroid_norm = np.linalg.norm(centroid) + 1e-9
        centroid = centroid / centroid_norm

        # Score each sentence: similarity to centroid
        # Higher = more representative of the cluster's overall content
        sims = sent_vecs @ centroid

        # Also score by informativeness (prefer sentences with named entities, numbers, etc.)
        inform_scores = []
        for s in unique_sentences:
            upper_words = sum(1 for w in s.split() if w[0].isupper() if len(w) > 1)
            has_numbers = bool(re.search(r"\d+", s))
            word_count = len(s.split())
            score = word_count / 30.0 + upper_words / 5.0 + (0.5 if has_numbers else 0)
            inform_scores.append(min(score, 2.0))
        inform_scores = np.array(inform_scores)

        # Combined: 70% representativeness + 30% informativeness
        combined_scores = 0.7 * sims + 0.3 * (inform_scores / inform_scores.max() if inform_scores.max() > 0 else 0)

        # Pick top 3 sentences, ensuring some diversity
        ranked_indices = np.argsort(-combined_scores)

        selected = []
        for idx in ranked_indices:
            if len(selected) >= 3:
                break
            # Avoid selecting very similar sentences to the ones already picked
            if selected:
                selected_vec = sent_vecs[idx]
                too_similar = False
                for sel_idx in selected:
                    if float(selected_vec @ sent_vecs[sel_idx]) > 0.85:
                        too_similar = True
                        break
                if not too_similar:
                    selected.append(int(idx))
            else:
                selected.append(int(idx))

        # Assemble the summary in original order (for coherence)
        selected.sort()
        selected_sentences = [unique_sentences[i] for i in selected]

        summary = " ".join(selected_sentences)
        if not summary.endswith("."):
            summary += "."
        return summary

    except Exception:
        logger.exception("Extractive summarization failed, falling back")
        combined = " ".join(snippets[:2]).strip()
        sentences = _SENTENCE_RE.split(combined)
        summary = ". ".join(s.strip() for s in sentences[:2] if s.strip())
        if summary and not summary.endswith("."):
            summary += "."
        return summary or "Details are still emerging."


def _why_it_matters(cluster: list[dict]) -> str:
    """
    Determine why a story matters using TF-IDF topic matching.
    
    Transforms the cluster's text using the pre-fitted TF-IDF vectorizer
    and compares against pre-computed topic description vectors
    to find the most relevant context.
    """
    combined_text = " ".join(
        a["title"] + ". " + a.get("content_snippet", "")[:200]
        for a in cluster[:5]
    )

    try:
        # Transform article text using pre-fitted vectorizer
        text_vec = _tfidf_vectorizer.transform([combined_text[:500]]).toarray()[0]
        text_norm = np.linalg.norm(text_vec) + 1e-9
        text_vec = text_vec / text_norm

        # Compute similarities against pre-computed topic vectors
        sims = _topic_vectors @ text_vec

        best_idx = int(np.argmax(sims))
        best_topic = _topic_names[best_idx]
        best_score = float(sims[best_idx])

        # Only use topic if similarity is above threshold
        if best_score > 0.3:
            return TOPIC_TEMPLATES.get(best_topic, TOPIC_TEMPLATES["default"])

        return TOPIC_TEMPLATES["default"]
    except Exception:
        # Fallback to keyword-based matching
        combined_titles = " ".join(a["title"] for a in cluster).lower()
        for keyword, template in TOPIC_TEMPLATES.items():
            if keyword == "default":
                continue
            if re.search(r"\b" + re.escape(keyword) + r"\b", combined_titles):
                return template
        return TOPIC_TEMPLATES["default"]

def summarize_stories(ranked_stories: list[dict]) -> list[dict]:
    """Enrich stories with headlines/summaries and pass through images."""
    results: list[dict] = []
    for story in ranked_stories:
        cluster = story["cluster"]
        title, url = _pick_headline(cluster)
        summary = _make_summary(cluster)
        why = _why_it_matters(cluster)

        # Pick the best image from the cluster: prefer the article whose headline
        # was chosen, otherwise the first article with an image_url
        image_url = None
        if cluster:
            # First try to find the article that matches our chosen URL
            for a in cluster:
                if a.get("url") == url and a.get("image_url"):
                    image_url = a["image_url"]
                    break
            # Fallback: first image found in cluster
            if not image_url:
                for a in cluster:
                    if a.get("image_url"):
                        image_url = a["image_url"]
                        break

        results.append({
            "title": title,
            "summary": summary,
            "why_it_matters": why,
            "url": url,
            "score": story["score"],
            "article_count": story["article_count"],
            "source": story["sources"],
            "published_at": story["latest_at"],
            "latest_at": story["latest_at"],
            "sectors": story.get("sectors", ["General"]),
            "image_url": image_url,
        })
    return results

