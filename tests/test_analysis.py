import pandas as pd

from analysis import (
    calculate_candidate_score,
    classify_grade,
    recommend_lender,
    get_lender_catalog,
)
from report_generator import generate_pdf_bytes


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


def test_lender_catalog_contains_verification_fields():
    catalog = get_lender_catalog()

    assert "lenders" in catalog
    assert catalog["lenders"]
    lender = catalog["lenders"][0]
    assert "approval_criteria" in lender
    assert "verification" in lender


def test_recommend_lender_mentions_verification_status():
    row = {
        "분석점수": 90,
        "분석등급": "A",
        "부채총액": 500000000,
        "KB시세": 1000000000,
        "근저당여부": "아니오",
        "압류여부": "아니오",
    }

    lender = recommend_lender(row)

    assert "검증" in lender or "실사" in lender


def test_report_generator_returns_nonempty_pdf_bytes():
    rows = [{
        "사건번호": "T-100",
        "주소": "서울시 강남구",
        "아파트명": "테스트 아파트",
        "감정가": 1000000000,
        "낙찰예상가": 900000000,
        "부채총액": 800000000,
        "권리요약": "근저당 존재",
        "분석점수": 85,
        "분석등급": "A",
        "담당자메모": "권리분석 기준: 기준 충족",
    }]

    pdf_bytes = generate_pdf_bytes(rows)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 100
