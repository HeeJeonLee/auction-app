# Auctiscope

Auctiscope는 “완전 자동화된 법률 판단”이 아니라, 경매 건을 선별하고 권리 리스크를 구조화해 사용자가 빠르게 판단할 수 있도록 돕는 전문가용 판단 보조 플랫폼입니다.
이 플랫폼은 우선 개인 수익 창출용으로 운영하고, 검증된 수익성과 운영성을 확보한 뒤 이후 상업화할 수 있도록 설계합니다.

## 목표
- 탱크옥션 경매 정보, KB시세, 권리 관련 캡처, 등기부 자료를 구조화한다.
- 경매 건을 우선순위별로 선별한다.
- 권리 리스크와 수익성 판단에 필요한 핵심 정보를 정리한다.
- 최종 권리분석과 사건 판단은 사용자 판단으로 남긴다.

## 핵심 원칙
- AI는 법률적 최종 결론을 내리지 않는다.
- AI는 정보 정리, 요약, 분류, 우선순위 제시를 담당한다.
- 모든 판단은 사용자가 최종 결정한다.
- 무료/로컬 AI 도구를 우선 활용한다.
- 캡처본 입력 후 권리분석까지 완료된 사건만 데이터로 보관하고, 기준 미달 건은 플랫폼이 데이터에서 삭제하며 나머지는 사용자가 삭제할 수 있도록 운영한다.

## 운영 규칙
1. 이미지 입력 후 OCR/비전 분석으로 구조화된 데이터를 즉시 생성한다.
2. 권리분석은 인터넷 공개 정보, 시세, 공공자료, 채권자 정보, 경매공고 정보를 종합해 전문가 수준의 객관적 분석으로 정리한다.
3. 채권자별 특징은 계속 업데이트해 분석 규칙으로 누적한다.
4. 부채총액이 KB시세의 85%를 초과하거나, 낙찰예상가 대비 90%를 초과하면 기본적으로 데이터 보관 대상에서 제외한다.
5. 취하 진행이 없거나 실무상 부적격으로 판정된 건은 사용자 판단에 따라 데이터 삭제 대상으로 분류한다.

## 주요 기능
- 경매 정보 수집 및 입력
- 이미지 업로드 및 OCR/비전 분석
- 권리 리스크 정리
- 경매 건 우선순위 점수 산출
- 전문가 검토용 리포트/보고서 생성
- 저장/검색/리뷰 큐 관리

## 아키텍처 요약
- UI: Streamlit(초기), 향후 React/Next.js 확장 가능
- Backend: Python + FastAPI
- DB: PostgreSQL(운영), SQLite/CSV(로컬 테스트)
- OCR: Tesseract / PaddleOCR
- Vision LLM: Ollama + Qwen2.5-VL 또는 Llama 3.2-Vision
- 임베딩/RAG: sentence-transformers + FAISS
- 문서 파싱: PyMuPDF / pdfplumber
- 규칙 엔진: Python 기반 결정 로직

## 실행 방법
1. `pip install -r requirements.txt`
2. `streamlit run app.py`

샘플 파이프라인 실행

1. 필요한 패키지 설치:
```powershell
cd auction_rescue_mvp
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

2. 샘플 데이터로 파이프라인 실행:
```powershell
.venv\Scripts\python.exe tools\run_sample_pipeline.py
```

결과: `outputs/processed.xlsx`, `outputs/top10.pptx`, `outputs/top10.pdf` 생성됩니다.
