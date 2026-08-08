import pandas as pd

from analysis import calculate_candidate_score, classify_grade, recommend_lender


def test_calculate_candidate_score_prefers_clear_liquidation_case():
    row = {
        "청산가능여부": "예",
        "낙찰예상가": 9000000000,
        "부채총액": 7000000000,
        "근저당여부": "아니오",
        "압류여부": "아니오",
        "가압류여부": "아니오",
        "가처분여부": "아니오",
        "임차권등기여부": "아니오",
        "전세권여부": "아니오",
    }

    score = calculate_candidate_score(row)

    assert score >= 80


def test_classify_grade_returns_lower_grade_for_risky_case():
    row = {
        "청산가능여부": "아니오",
        "낙찰예상가": 5000000000,
        "부채총액": 8000000000,
        "근저당여부": "예",
        "압류여부": "예",
        "가압류여부": "아니오",
        "가처분여부": "아니오",
        "임차권등기여부": "예",
        "전세권여부": "아니오",
    }

    score = calculate_candidate_score(row)
    grade = classify_grade(score)

    assert score <= 60
    assert grade == "C"


def test_recommend_lender_prefers_aggressive_lender_for_high_score_case():
    row = {
        "분석점수": 90,
        "분석등급": "A",
    }

    lender = recommend_lender(row)

    assert lender == "대주A"
