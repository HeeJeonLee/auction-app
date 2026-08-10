from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import enrich_dataframe


def main() -> None:
    src = str(ROOT_DIR / "data" / "validation_hold_and_approval.csv")
    df = pd.read_csv(src)
    out = enrich_dataframe(df)

    for _, row in out.iterrows():
        print(
            "VALIDATION_RESULT::"
            f"file={row.get('원본파일명','')}|"
            f"case={row.get('사건번호','')}|"
            f"verdict={row.get('규칙판정','')}|"
            f"status={row.get('심사상태','')}|"
            f"approval={row.get('최종승인','')}|"
            f"evidence={str(row.get('규칙근거',''))[:220]}"
        )


if __name__ == "__main__":
    main()
