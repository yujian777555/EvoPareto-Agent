"""GSM8K real-task propagation and gold scoring tests (Task 4)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.benchmark.gsm8k_protocol import split_manifest
from src.benchmark.gsm8k_tasks import (
    evaluate_workflow_output,
    extract_final_answer,
    load_offline_tasks,
    score_answer,
    task_by_id,
)


def test_offline_tasks_have_gold_and_question():
    tasks = load_offline_tasks()
    assert len(tasks) >= 8
    for t in tasks:
        assert t.task_id and t.question and t.gold_answer
        assert len(t.question) > 20
        # gold is a normalised number
        float(t.gold_answer.replace(",", ""))


def test_split_isolation_in_task_pack():
    tasks = load_offline_tasks()
    search = [t.task_id for t in tasks if t.split == "search"]
    val = [t.task_id for t in tasks if t.split == "validation"]
    test = [t.task_id for t in tasks if t.split == "test"]
    assert search and val and test
    assert not set(search) & set(test)
    assert not set(val) & set(test)
    # protocol agrees test is held out
    m = split_manifest()
    assert m["selection_uses_official_test_set"] is False


def test_extract_final_answer_forms():
    assert extract_final_answer("blah #### 42") == "42"
    assert extract_final_answer("answer is -17") == "-17"
    assert extract_final_answer("total 1,234 dollars") == "1234"
    assert extract_final_answer("about 3.14") == "3.14"
    assert extract_final_answer("#### 18.0") == "18"
    assert extract_final_answer("no numbers here") is None
    assert extract_final_answer(None) is None


def test_gold_scoring_exact_match():
    assert score_answer("72", "72")["correct"] is True
    assert score_answer("1,234", "1234")["correct"] is True
    assert score_answer("18.0", "18")["correct"] is True
    assert score_answer("17", "18")["correct"] is False
    assert score_answer(None, "18")["correct"] is False
    assert score_answer(None, "18")["reason"] == "NO_ANSWER_EXTRACTED"


def test_invalid_output_stays_in_denominator():
    t = task_by_id("gsm8k-train-0000")
    ev = evaluate_workflow_output(t, "I cannot solve this")
    assert ev["correct"] is False
    assert ev["reason"] == "NO_ANSWER_EXTRACTED"
    assert ev["task_id"] == "gsm8k-train-0000"


def test_real_question_reaches_evaluator():
    t = task_by_id("gsm8k-train-0001")
    ev = evaluate_workflow_output(t, "The answer is #### 10")
    assert ev["correct"] is True
    assert ev["question_len"] == len(t.question)


def test_hardcoded_constant_answers_not_used():
    """Scoring must compare against per-task gold, not a global constant."""
    t1 = task_by_id("gsm8k-train-0000")
    t2 = task_by_id("gsm8k-train-0001")
    assert t1.gold_answer != t2.gold_answer
    assert evaluate_workflow_output(t1, "#### 72")["correct"] is True
    assert evaluate_workflow_output(t1, "#### 10")["correct"] is False
    assert evaluate_workflow_output(t2, "#### 10")["correct"] is True
