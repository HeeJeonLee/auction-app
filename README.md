# 핸드폰 캡쳐로 앱적용(50억까지)

이 프로젝트는 휴대폰에서 탱크옥션 캡처를 업로드해 경매취하 후보를 관리하는 MVP입니다. 적용 범위는 5억~50억원대 물건을 우선 대상으로 하며, 권리분석·대주 추천·영업 우선순위까지 정리할 수 있습니다.

## 기능
- 엑셀 업로드
- 후보 목록 편집
- 자동 분석 점수/등급 계산
- 추천 대주 자동 분류
- 권리 요약 자동 생성
- 후보 여부 자동 추천
- 저장/초기화/요약 통계

## 실행 방법
1. `pip install -r requirements.txt`
2. `streamlit run app.py`

샘플 파이프라인(자동 삭제 및 PDF/PPT 생성) 실행

1. 필요한 패키지 설치:
```powershell
cd auction_rescue_mvp
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

2. 샘플 데이터로 파이프라인 실행:
```powershell
.venv\Scripts\python.exe tools\run_sample_pipeline.py
```

결과: `auction_rescue_mvp/outputs/processed.xlsx`, `top10.pptx`, `top10.pdf` 생성 및 자동 삭제된 행 수 출력.

주의: 자동 삭제 정책은 기본적으로 삭제 전 `outputs/deleted` 폴더로 이동(감사용 저장)합니다. 영구삭제를 원하면 환경변수 `PERMANENT_DELETE=1`을 설정하고 실행하세요. 예:

```powershell
setx PERMANENT_DELETE 1
.venv\Scripts\python.exe tools\run_sample_pipeline.py
```

경고: `PERMANENT_DELETE=1` 설정 시 자동으로 미통과된 행은 복구 불가하게 폐기됩니다. 운영 전 샘플 데이터로 충분히 검증하시기 바랍니다.
