import logging
import numpy as np
from hdbscan import HDBSCAN
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from config import CLUSTER_THRESHOLD

logger = logging.getLogger(__name__)


def _build_text(article: dict) -> str:
    title = article.get("title", "")
    snippet = article.get("content_snippet", "")
    return f"{title}. {snippet}" if snippet else title


def _get_tfidf_embeddings(texts: list[str]) -> np.ndarray:
    """Compute TF-IDF feature vectors for a list of texts.

    TF-IDF is deterministic and instant — no model download, no GPU needed.
    Returns a dense numpy array compatible with cosine similarity and HDBSCAN.
    """
    vectorizer = TfidfVectorizer(
        max_features=500,
        stop_words="english",
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(texts)
    return tfidf_matrix.toarray()


def _extract_topics(texts: list[str], n_topics: int = 5) -> list[int]:
    """Extract latent topics using LDA."""
    if len(texts) < 3 or n_topics < 2:
        return [0] * len(texts)

    try:
        vectorizer = CountVectorizer(max_df=0.85, min_df=1, stop_words="english", max_features=500)
        dtm = vectorizer.fit_transform(texts)

        n_components = min(n_topics, dtm.shape[0] - 1, dtm.shape[1] - 1)
        if n_components < 2:
            return [0] * len(texts)

        lda = LatentDirichletAllocation(
            n_components=n_components, random_state=42,
            max_iter=100,              # 200 → 100: converges well on small corpuses
            evaluate_every=-1,         # skip perplexity eval (saves ~30% time)
            verbose=False,
        )
        topic_dist = lda.fit_transform(dtm)
        return topic_dist.argmax(axis=1).tolist()
    except Exception as e:
        logger.warning(f"Topic modeling failed: {e}")
        return [0] * len(texts)


def cluster_articles(articles: list[dict]) -> list[list[dict]]:
    """Cluster articles using HDBSCAN + topic modeling + TF-IDF features.

    TF-IDF replaces sentence-transformers — no model download, instant startup,
    works great on news headlines which have clear topic keywords.

    Deduplication happens using the same TF-IDF vectors.
    """
    if not articles:
        return []

    try:
        if len(articles) < 2:
            return [[a] for a in articles]

        # Build text representations for all articles
        texts = [_build_text(a) for a in articles]

        # 1. Compute TF-IDF feature vectors (replaces sentence-transformers embeddings)
        embeddings = _get_tfidf_embeddings(texts)

        # 2. Deduplicate using cosine similarity on TF-IDF vectors
        if len(articles) > 1:
            sim_matrix = cosine_similarity(embeddings)
            kept_indices: set[int] = set()
            for i in range(len(articles)):
                if i in kept_indices:
                    continue
                duplicates = [
                    j for j in range(i + 1, len(articles))
                    if sim_matrix[i][j] > 0.92
                ]
                if duplicates:
                    candidates = [i] + duplicates
                    best = max(candidates, key=lambda idx: len(articles[idx].get("content_snippet", "")))
                    kept_indices.add(best)
                else:
                    kept_indices.add(i)

            sorted_kept = sorted(kept_indices)
            articles = [articles[i] for i in sorted_kept]
            embeddings = embeddings[sorted_kept]
            texts = [texts[i] for i in sorted_kept]

        if len(articles) < 2:
            return [[a] for a in articles]

        # 3. Extract latent topics from article text
        n_topics = max(2, min(8, len(articles) // 5))
        topic_labels = _extract_topics(texts, n_topics=n_topics)

        # 4. Augment embeddings with topic features
        n_topics_actual = len(set(topic_labels))
        if n_topics_actual > 1:
            topic_onehot = np.zeros((len(articles), n_topics_actual))
            for i, label in enumerate(topic_labels):
                topic_onehot[i, label] = 1.0
            embeddings = np.concatenate([embeddings, topic_onehot * 0.3], axis=1)

        # 5. HDBSCAN clustering (tuned for speed with TF-IDF vectors)
        min_cluster_size = max(2, len(articles) // 30)
        clusterer = HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=2,              # 1 → 2: reduces noise-processing overhead
            metric="euclidean",
            cluster_selection_epsilon=CLUSTER_THRESHOLD,
            prediction_data=False,      # False: skip approximate_predict training (not used downstream)
            core_dist_n_jobs=-1,        # use all CPU cores
        )
        labels = clusterer.fit_predict(embeddings)

        # 6. Build clusters
        clusters_dict: dict[int | str, list[dict]] = {}
        for i, label in enumerate(labels):
            if label == -1:
                cluster_key = f"noise_{i}"
                clusters_dict.setdefault(cluster_key, []).append(articles[i])
            else:
                clusters_dict.setdefault(label, []).append(articles[i])

        clusters = list(clusters_dict.values())
        noise_count = sum(1 for l in labels if l == -1)
        logger.info(
            f"HDBSCAN created {len(clusters)} clusters "
            f"(noise: {noise_count} articles out of {len(articles)})"
        )
        return clusters

    except Exception as e:
        logger.exception(f"Clustering failed: {e}")
        return [[a] for a in articles]
