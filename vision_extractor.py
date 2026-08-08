import os
import json
import pandas as pd
import google.generativeai as genai
from typing import List, Any

def process_images_to_dataframe(api_key: str, image_files: List[Any], default_columns: List[str]) -> pd.DataFrame:
    """최고위 전문가용: 여러 장의 이미지를 파싱하고, 무조건 1개 이상의 데이터를 반환하도록 강제합니다."""
    if not api_key:
        raise ValueError("Gemini API 키가 필요합니다.")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-pro')

    prompt = """
    당신은 최상위 부동산 NPL 전문가 및 투자 심사역입니다.
    제공된 이미지에서 경매 물건의 핵심 정보를 추출하여 JSON 배열(Array)로 반환하십시오.
    *중요*: 이미지에 글씨가 희미하거나 완벽하지 않아도 절대 빈 배열([])을 반환하지 마십시오. 추정할 수 있는 한계 내에서 최대한 필드를 채워 1개 이상의 객체를 만드십시오. 정 찾기 어렵다면 사건번호에 "미상"이라고 적더라도 객체를 생성해야 합니다.

    [필수 추출 데이터 (숫자형은 콤마 없이 작성, 모를 경우 0 또는 빈 문자열)]
    - 원본파일명 (제공된 이미지의 파일명을 그대로 기재. 모르면 빈 문자열)
    - 사건번호 (없으면 "미상")
    - 매각기일 (예: 2026-08-30)
    - 법원명
    - 물건번호
    - 주소
    - 아파트명
    - 감정가
    - 최저매각가격
    - 낙찰예상가
    - 부채총액 (청구금액+기타 설정액 등 추정)
    - KB시세
    - 주요채권자
    
    [권리 위험도 평가 (있으면 "예", 없으면 "아니요")]
    - 청산가능여부
    - 근저당여부
    - 압류여부
    - 가압류여부
    - 가처분여부
    - 임차권등기여부
    - 전세권여부
    - 가등기여부

    [★ 전문가 심층 종합 의견]
    - AI_심층분석: "시세 대비 부채비율(LTV), 지역적 낙찰가율 통계, 명도 난이도, 주요 권리상 하자 등을 고려한 3~4문장의 최고급 리스크 평가 (매우 날카롭고 전문적인 금융/법적 용어 사용)"

    JSON 예시:
    [
      {
        "원본파일명": "image_123.jpg",
        "사건번호": "2023타경1234",
        "감정가": "500000000",
        "부채총액": "450000000",
        "AI_심층분석": "현재 부채총액이 감정가에 육박하나..."
      }
    ]
    """

    image_parts = []
    # 용량 최적화 (사진이 너무 많거나 클 경우 대비)
    for img_file in image_files:
        ext = img_file.name.lower()
        mime_type = "image/jpeg" if ext.endswith(('jpg', 'jpeg')) else "image/png"
        image_parts.append({
            "mime_type": mime_type,
            "data": img_file.getvalue()
        })
        # AI에게 파일명을 알려주기 위해 텍스트 파트도 추가
        image_parts.append(f"이 이미지의 파일명은 '{img_file.name}' 입니다.")

    try:
        response = model.generate_content([prompt] + image_parts)
        result_text = response.text.replace("```json", "").replace("```", "").strip()
        
        try:
            parsed_data = json.loads(result_text)
        except:
            # 완전 실패 시 하드코딩된 에러 배열 반환
            parsed_data = [{"사건번호": "판독불가", "AI_심층분석": "[오류] AI가 사진에서 텍스트를 파싱하는 데 실패했습니다. 원본 캡쳐를 수동으로 확인하십시오."}]

        if not parsed_data or len(parsed_data) == 0:
            parsed_data = [{"사건번호": "정보없음", "AI_심층분석": "[경고] 제공된 캡쳐 파일에서 명확한 부동산 법원 경매 데이터를 찾지 못했습니다. 그러나 증빙 캡쳐본 보관함에 사진은 저장되었습니다."}]

        if isinstance(parsed_data, dict):
            parsed_data = [parsed_data]
            
        extracted_rows = []
        for data in parsed_data:
            row = {col: "" for col in default_columns}
            for key, value in data.items():
                if key in row:
                    row[key] = value
            row["AI_심층분석"] = data.get("AI_심층분석", "")
            extracted_rows.append(row)

        return pd.DataFrame(extracted_rows)
        
    except Exception as e:
        raise Exception(f"AI 심층 구조화 파싱 실패: {e}")
