"""
Conflict Resolver: groups semantically similar claims, applies strategy,
and returns a list of resolved claims + unresolved conflicts.
"""
from __future__ import annotations
import numpy as np
from sentence_transformers import SentenceTransformer
from db.models import DocumentRecord, Claim, Conflict, CredibilityScore
from conflict.strategies import STRATEGIES, DEFAULT_STRATEGY_BY_TYPE

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _cluster_claims(claims: list[Claim], threshold: float = 0.82) -> list[list[Claim]]:
    """Greedy single-linkage clustering by semantic similarity."""
    if not claims:
        return []
    model = _get_model()
    texts = [c.text for c in claims]
    embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

    clusters: list[list[int]] = []
    assigned = [False] * len(claims)

    for i in range(len(claims)):
        if assigned[i]:
            continue
        cluster = [i]
        assigned[i] = True
        for j in range(i + 1, len(claims)):
            if not assigned[j]:
                sim = _cosine_sim(embeddings[i], embeddings[j])
                if sim >= threshold:
                    cluster.append(j)
                    assigned[j] = True
        clusters.append(cluster)

    return [[claims[i] for i in cluster] for cluster in clusters]


def resolve_conflicts(
    docs: list[DocumentRecord],
    strategy_override: str | None = None,
) -> tuple[list[Claim], list[Conflict]]:
    """
    Main entry point for conflict resolution.

    Returns:
        resolved_claims: one winning claim per cluster (where unambiguous)
        conflicts: list of Conflict objects (both resolved and unresolved)
    """
    # Build credibility map
    cred_map: dict[str, CredibilityScore] = {
        doc.doc_id: doc.credibility_score or CredibilityScore(overall=0.5)
        for doc in docs
    }

    # Determine dominant doc type to select default strategy
    type_counts: dict[str, int] = {}
    for doc in docs:
        type_counts[doc.doc_type] = type_counts.get(doc.doc_type, 0) + 1
    dominant_type = max(type_counts, key=type_counts.get) if type_counts else "unknown"

    strategy_name = strategy_override or DEFAULT_STRATEGY_BY_TYPE.get(dominant_type, "weighted_vote")
    strategy_fn = STRATEGIES.get(strategy_name, STRATEGIES["weighted_vote"])

    # Collect all claims
    all_claims: list[Claim] = [claim for doc in docs for claim in doc.claims]

    if not all_claims:
        return [], []

    clusters = _cluster_claims(all_claims)

    resolved_claims: list[Claim] = []
    conflicts: list[Conflict] = []

    for cluster in clusters:
        if len(cluster) == 1:
            # No conflict — single source claim
            resolved_claims.append(cluster[0])
            continue

        # Check if same source doc (no conflict, just repetition)
        unique_sources = {c.source_doc_id for c in cluster}
        if len(unique_sources) == 1:
            resolved_claims.append(cluster[0])
            continue

        # Multiple sources discuss same topic — potential conflict
        conflict = strategy_fn(cluster, cred_map)
        conflict.topic = cluster[0].text[:80] + "…"

        conflicts.append(conflict)
        if conflict.status == "resolved" and conflict.resolution:
            resolved_claims.append(
                Claim(text=conflict.resolution, source_doc_id=cluster[0].source_doc_id, confidence=conflict.confidence)
            )
        else:
            # Unresolved: include top-credibility claim but flag it
            best = max(cluster, key=lambda c: cred_map.get(c.source_doc_id, CredibilityScore(overall=0)).overall)
            resolved_claims.append(Claim(text=best.text, source_doc_id=best.source_doc_id, confidence=0.4))

    return resolved_claims, conflicts
