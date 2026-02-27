"""Tests for conflict resolution strategies."""
import pytest
from db.models import Claim, CredibilityScore
from conflict.strategies import (
    weighted_vote, majority_vote, highest_credibility_wins, conservative
)

DOC_A = "doc-aaa"
DOC_B = "doc-bbb"
DOC_C = "doc-ccc"

CLAIMS = [
    Claim(text="The drug reduces mortality by 30%.", source_doc_id=DOC_A),
    Claim(text="The drug has no significant effect on mortality.", source_doc_id=DOC_B),
    Claim(text="The drug shows modest 12% reduction in mortality.", source_doc_id=DOC_C),
]

CRED_MAP_CLEAR = {
    DOC_A: CredibilityScore(overall=0.90),
    DOC_B: CredibilityScore(overall=0.40),
    DOC_C: CredibilityScore(overall=0.55),
}

CRED_MAP_CLOSE = {
    DOC_A: CredibilityScore(overall=0.75),
    DOC_B: CredibilityScore(overall=0.72),
    DOC_C: CredibilityScore(overall=0.70),
}


def test_weighted_vote_clear_winner():
    result = weighted_vote(CLAIMS, CRED_MAP_CLEAR)
    assert result.status == "resolved"
    assert result.resolution == CLAIMS[0].text  # DOC_A wins with 0.90


def test_weighted_vote_too_close():
    result = weighted_vote(CLAIMS, CRED_MAP_CLOSE, threshold=0.15)
    assert result.status == "unresolved"
    assert result.resolution is None


def test_majority_vote_two_high_trust():
    high_cred = {
        DOC_A: CredibilityScore(overall=0.90),
        DOC_B: CredibilityScore(overall=0.88),
        DOC_C: CredibilityScore(overall=0.20),
    }
    result = majority_vote(CLAIMS, high_cred, high_trust_threshold=0.75)
    assert result.status == "resolved"
    assert result.confidence == 0.85


def test_highest_credibility_wins():
    result = highest_credibility_wins(CLAIMS, CRED_MAP_CLEAR)
    assert result.status == "resolved"
    assert result.resolution == CLAIMS[0].text


def test_conservative_always_unresolved():
    result = conservative(CLAIMS, CRED_MAP_CLEAR)
    assert result.status == "unresolved"
    assert result.confidence == 0.0


def test_empty_claims():
    result = weighted_vote([], CRED_MAP_CLEAR)
    assert result.status == "unresolved"
