import os
import json
import base64
import pandas as pd
import google.generativeai as genai
from typing import List, Dict, Any
from io import BytesIO

def extract_data_from_image_gemini(api_key: str, image_bytes: bytes) -> dict:
    """
    Gemini Vision API를 사용하여 이미지(경매 캡쳐)에서 엑셀 형식의 데이터를 추출합니다.
    """
    if not api_key:
        raise ValueError("Gemini API 키가 필요합니다.")

    genai.configure(api_key=api_key)
    
    # Use Gemini 1.5 Pro as it's best for complex parsing and structured output
    model = genai.GenerativeModel('gemini-1.5-pro')

    prompt = """
    당신은 부동산 경매 전문가 및 데이터 추출 AI입니다. 
    제공된 이미지(부동산 경매 정보 캡쳐)를 분석하여 아래 요구하는 필드들을 추출하고, 반드시 지정된 JSON 형식으로만 응답하세요.
    마크다운(```json 등)을 포함하지 말고, 순수한 JSON 객체만 반환해야 합니다.

    추출해야 할 필드 (찾을 수 없는 경우 ""(빈 문자열) 반환):
    - 사건번호
    - 법원명
    - 물건번호
    - 주소
    - 아파트명
    - 감정가 (숫자만, 예: 1000000000)
    - 최저매각가격 (숫자만)
    - 낙찰예상가 (숫자만)
    - 부채총액 (숫자만)
    - KB시세 (숫자만)
    - 주요채권자 (이름)
    
    다음 권리 분석 필드들은 있다면 "예", 없다면 "아니요"로 반환하세요:
    - 청산가능여부 (알 수 없으면 빈 문자열)
    - 근저당여부
    - 압류여부
    - 가압류여부
    - 가처분여부
    - 임차권등기여부
    - 전세권여부
    - 가등기여부

    JSON 형식 예시:
    {
      "사건번호": "2023타경1234",
      "감정가": "500000000",
      "근저당여부": "예",
      ...
    }
    """

    # Prepare the image parts
    image_parts = [
        {
            "mime_type": "image/jpeg",
            "data": image_bytes
        }
    ]

    try:
        response = model.generate_content([prompt, image_parts[0]])
        # Clean up the output in case it includes markdown
        result_text = response.text.replace("```json", "").replace("```", "").strip()
        parsed_data = json.loads(result_text)
        return parsed_data
    except Exception as e:
        raise Exception(f"Vision API 추출 중 오류 발생: {e}")

def process_images_to_dataframe(api_key: str, image_files: List[Any], default_columns: List[str]) -> pd.DataFrame:
    """여러 장의 이미지를 분석하여 데이터프레임으로 합칩니다."""
    extracted_rows = []
    
    for img_file in image_files:
        try:
            img_bytes = img_file.getvalue()
            data = extract_data_from_image_gemini(api_key, img_bytes)
            
            row = {col: "" for col in default_columns}
            for key, value in data.items():
                if key in row:
                    row[key] = value
            
            extracted_rows.append(row)
        except Exception as e:
            print(f"Failed to process {img_file.name}: {e}")
            # Could throw or log
            
    return pd.DataFrame(extracted_rows, columns=default_columns)
