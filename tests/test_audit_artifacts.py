"""Phase5-Audit-3/4/5 tests."""

import json
from pathlib import Path

import pytest

from src.agent.genome import AgentGenome
from src.benchmark.real_world_agent import _build_catalog


def test_transfer_results_file():
    p = Path(__file__).resolve().parents[2] / "results" / "audit" / "peem_transfer.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        assert "summary" in d and "verdict" in d
        assert set(d["summary"]) == {"random", "fresh_peem", "transfer_peem"}


def test_genotype_evolution_file():
    p = Path(__file__).resolve().parents[2] / "results" / "audit" / "genotype_evolution.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        assert "genotype_frequency" in d
        assert d["genotype_frequency"][0]["unique_genotypes"] > 1


def test_difficulty_review_file():
    p = Path(__file__).resolve().parents[2] / "results" / "audit" / "difficulty_review.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        assert "saturation_check" in d
        assert "hard_profile" in d


def test_catalog_difficulties_bounded():
    for t in _build_catalog():
        assert 0 < t["difficulty"] <= 1


def test_credit_attribution_file():
    p = Path(__file__).resolve().parents[2] / "results" / "audit" / "credit_attribution.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        assert "verdict" in d
        assert "limitations" in d
