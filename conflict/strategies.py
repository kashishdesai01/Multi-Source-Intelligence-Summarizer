"""Conflict resolution strategies — pluggable per doc type."""
from __future__ import annotations
from db.models import Claim, Conflict, CredibilityScore


def weighted_vote(
    claims: list[Claim],
    credibility_map: dict[str, CredibilityScore],
    threshold: float = 0.15,
) -> Conflict:
    """
    Pick the claim whose source doc has the highest credibility score.
    If all doc scores are within `threshold` of each other → mark unresolved.
    """
    if not claims:
        return Conflict(claims=[], topic="", status="unresolved")

    scored = [(c, credibility_map.get(c.source_doc_id, CredibilityScore(overall=0.5))) for c in claims]
    scored.sort(key=lambda x: x[1].overall, reverse=True)

    best_claim, best_cred = scored[0]
    scores = [s.overall for _, s in scored]
    score_range = max(scores) - min(scores)

    conflict = Conflict(
        claims=claims,
        topic="",
        resolution=best_claim.text,
        confidence=best_cred.overall,
    )

    if score_range < threshold:
        conflict.status = "unresolved"
        conflict.resolution = None
    else:
        conflict.status = "resolved"

    return conflict


def majority_vote(
    claims: list[Claim],
    credibility_map: dict[str, CredibilityScore],
    high_trust_threshold: float = 0.75,
) -> Conflict:
    """
    If ≥2 high-trust sources agree semantically, that claim wins.
    Otherwise fall back to weighted_vote.
    """
    high_trust = [c for c in claims if credibility_map.get(c.source_doc_id, CredibilityScore(overall=0)).overall >= high_trust_threshold]
    if len(high_trust) >= 2:
        winner = high_trust[0]
        return Conflict(
            claims=claims,
            topic="",
            resolution=winner.text,
            status="resolved",
            confidence=0.85,
        )
    return weighted_vote(claims, credibility_map)


def highest_credibility_wins(
    claims: list[Claim],
    credibility_map: dict[str, CredibilityScore],
) -> Conflict:
    """Always pick the highest-credibility source, no threshold check."""
    if not claims:
        return Conflict(claims=[], topic="", status="unresolved")
    best = max(claims, key=lambda c: credibility_map.get(c.source_doc_id, CredibilityScore(overall=0)).overall)
    return Conflict(
        claims=claims,
        topic="",
        resolution=best.text,
        status="resolved",
        confidence=credibility_map.get(best.source_doc_id, CredibilityScore(overall=0.5)).overall,
    )


def conservative(
    claims: list[Claim],
    credibility_map: dict[str, CredibilityScore],
) -> Conflict:
    """Flag any disagreement as unresolved — safest for high-stakes summaries."""
    return Conflict(
        claims=claims,
        topic="",
        resolution=None,
        status="unresolved",
        confidence=0.0,
    )


STRATEGIES: dict[str, callable] = {
    "weighted_vote": weighted_vote,
    "majority_vote": majority_vote,
    "highest_credibility_wins": highest_credibility_wins,
    "conservative": conservative,
}

DEFAULT_STRATEGY_BY_TYPE: dict[str, str] = {
    "research_paper": "weighted_vote",
    "news_article": "majority_vote",
    "blog_post": "weighted_vote",
    "legal_document": "highest_credibility_wins",
    "unknown": "conservative",
}
