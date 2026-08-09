# OCR Engine Benchmark Report

- Ground truth: C:\Users\aplus\Desktop\경매취하 AI 분석.대주 매칭시스템\auction_rescue_mvp\data\benchmark\ground_truth.csv
- Engines compared: 2

## Overall

- gemini: overall 15.38%, matched 3/3
- local_hybrid: overall 15.38%, matched 3/3

## Field Accuracy

| Engine | 법원명 | 물건번호 | 주소 | 아파트명 | 감정가 | 최저매각가격 | 부채총액 | KB시세 | 주요채권자 | 근저당여부 | 압류여부 | 가압류여부 | 가처분여부 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| local_hybrid | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Field Coverage

| Engine | 법원명 | 물건번호 | 주소 | 아파트명 | 감정가 | 최저매각가격 | 부채총액 | KB시세 | 주요채권자 | 근저당여부 | 압류여부 | 가압류여부 | 가처분여부 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| local_hybrid | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Numeric MAPE (Lower is better)

| Engine | 감정가 | 최저매각가격 | 부채총액 | KB시세 |
|---|---|---|---|---|
| gemini | 0.0 | 0.0 | 0.0 | 0.0 |
| local_hybrid | 0.0 | 0.0 | 0.0 | 0.0 |