import os
import json
import base64
import pandas as pd
import google.generativeai as genai
from typing import List, Dict, Any
from io import BytesIO

def process_images_to_dataframe(api_key: str, image_files: List[Any], default_columns: List[str]) -> pd.DataFrame:
    """최고위 전문가용: 여러 장의 이미지를 파싱하고, NPL 및 대주 매칭을 위한 딥 러닝 심층 분석을 제공합니다."""
    if not api_key:
        raise ValueError("Gemini API 키가 필요합니다.")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-pro')

    prompt = """
    당신은 최상위 부동산 NPL 전문가 및 투자 심사역(Senior Underwriter)입니다.
    제공된 이미지(경매 물건 정보)를 정밀 분석하여, 각 물건별로 아래 JSON 배열(Array) 형태의 구조화된 데이터를 추출하십시오.

    [필수 추출 데이터 (숫자형은 콤마 없이 작성, 모를 경우 빈 문자열)]
    - 사건번호 (예: 2023타경1234)
    - 매각기일 (예: 2026-08-30. 화면에 입찰/매각기일이 보이면 반드시 추출)
    - 법원명
    - 물건번호
    - 주소
    - 아파트명
    - 감정가
    - 최저매각가격
    - 낙찰예상가 (없으면 해당 지역의 최근 낙찰가율 동향을 반영하여 전문가적 관점에서 추정)
    - 부채총액 (청구금액+기타 설정액 등 총 채무액 추정)
    - KB시세 (없으면 감정가로 대체)
    - 주요채권자 (이름/기관명)
    
    [권리 위험도 평가 (있으면 "예", 없으면 "아니요")]
    - 청산가능여부 (법적 하자가 심각하여 완전 불가능한 경우가 아니면 "예")
    - 근저당여부
    - 압류여부
    - 가압류여부
    - 가처분여부
    - 임차권등기여부
    - 전세권여부
    - 가등기여부

    [★ 전문가 심층 종합 의견 (이 필드는 반드시 작성해야 함)]
    - AI_심층분석: "시세 대비 부채비율(LTV), 지역적 낙찰가율 통계, 명도 난이도, 주요 권리상 하자(가등기/가처분 등)의 인수 가능성 등을 종합적으로 고려한 3~4문장의 전문가적 리스크 평가 및 매입/대환 타당성 의견 (어조는 매우 날카롭고 전문적인 금융/법적 용어 사용)"

    JSON 예시:
    [
      {
        "사건번호": "2023타경1234",
        "매각기일": "2026-08-30",
        ...
        "AI_심층분석": "현재 부채총액이 감정가를 상회하는 깡통전세 위험군이나, 선순위 채권자의 채권최고액을 고려 시 실제 피담보채무액은 낮을 가능성 존재. 다만 임차권등기가 설정되어 명도 저항 리스크가 높으므로 NPL 론세일 접근 시 보수적인 LTV 적용(80% 미만) 편성이 요구됨."
      }
    ]
    """

    image_parts = []
    for img_file in image_files:
        ext = img_file.name.lower()
        mime_type = "image/jpeg" if ext.endswith(('jpg', 'jpeg')) else "image/png"
        image_parts.append({
            "mime_type": mime_type,
            "data": img_file.getvalue()
        })

    try:
        response = model.generate_content([prompt] + image_parts)
        result_text = response.text.replace("```json", "").replace("```", "").strip()
        parsed_data = json.loads(result_text)
        
        if isinstance(parsed_data, dict):
            parsed_data = [parsed_data]
            
        extracted_rows = []
        for data in parsed_data:
            row = {col: "" for col in default_columns}
            for key, value in data.items():
                if key in row:
                    row[key] = value
            # Map the new expert field to the dataframe
            row["AI_심층분석"] = data.get("AI_심층분석", "")
            extracted_rows.append(row)

        return pd.DataFrame(extracted_rows)
        
    except Exception as e:
        raise Exception(f"AI 심층 구조화 파싱 실패: {e}")
