import argparse
from pathlib import Path
from typing import List

import pandas as pd

from vision_extractor import process_images_to_dataframe


DEFAULT_COLUMNS = [
    "원본파일명",
    "사건번호",
    "법원명",
    "물건번호",
    "주소",
    "아파트명",
    "감정가",
    "최저매각가격",
    "낙찰예상가",
    "부채총액",
    "KB시세",
    "주요채권자",
    "근저당여부",
    "압류여부",
    "가압류여부",
    "가처분여부",
    "AI_심층분석",
]

BENCH_FIELDS = [
    "사건번호",
    "법원명",
    "물건번호",
    "주소",
    "아파트명",
    "감정가",
    "최저매각가격",
    "부채총액",
    "KB시세",
    "주요채권자",
    "근저당여부",
    "압류여부",
    "가압류여부",
    "가처분여부",
]


class LocalUpload:
    def __init__(self, path: Path):
        self.path = path
        self.name = path.name

    def getvalue(self) -> bytes:
        return self.path.read_bytes()


def list_images(folder: Path) -> List[Path]:
    images = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        images.extend(folder.glob(ext))
    return sorted(images)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate OCR prediction CSV for benchmark")
    parser.add_argument("--images", required=True, help="Folder containing capture images")
    parser.add_argument(
        "--engine",
        default="local_hybrid",
        choices=["auto", "gemini", "local_hybrid"],
        help="OCR engine to run",
    )
    parser.add_argument(
        "--mode",
        default="text_first",
        choices=["text_first", "balanced"],
        help="Image preprocessing mode",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output CSV path. Default: data/benchmark/predictions/{engine}.csv",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Gemini API key (required if --engine gemini)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    image_dir = Path(args.images)
    if not image_dir.is_absolute():
        image_dir = (root / image_dir).resolve()

    if not image_dir.exists():
        raise FileNotFoundError(f"Image folder not found: {image_dir}")

    files = [LocalUpload(p) for p in list_images(image_dir)]
    if not files:
        raise ValueError(f"No image files found in: {image_dir}")

    output_path = Path(args.output) if args.output else root / "data" / "benchmark" / "predictions" / f"{args.engine}.csv"
    if not output_path.is_absolute():
        output_path = (root / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    api_key = args.api_key
    if args.engine == "gemini" and not api_key:
        raise ValueError("--engine gemini requires --api-key")

    df = process_images_to_dataframe(
        api_key=api_key,
        image_files=files,
        default_columns=DEFAULT_COLUMNS,
        mode=args.mode,
        engine=args.engine,
    )

    for col in BENCH_FIELDS:
        if col not in df.columns:
            df[col] = ""

    out_df = df[BENCH_FIELDS].copy()
    out_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"Prediction CSV written: {output_path}")
    print(f"Rows: {len(out_df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
