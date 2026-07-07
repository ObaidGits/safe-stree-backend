#!/usr/bin/env python3
"""Download or verify the OpenVINO models used by the gender pipeline."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import FACE_MODEL_PATH, GENDER_MODEL_PATH


FACE_MODEL_NAME = "face-detection-retail-0004"
GENDER_MODEL_NAME = "age-gender-recognition-retail-0013"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set up the SafeStree gender model files")
    parser.add_argument(
        "--output-dir",
        default=str(Path("data/models/openvino")),
        help="Directory where the Open Model Zoo models should be stored",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands without downloading anything",
    )
    return parser.parse_args()


def _resolve_expected_xml(model_path: str) -> Path:
    path = Path(model_path)
    search_roots = []
    if path.exists() and path.is_dir():
        search_roots.append(path)
    if path.parent.exists():
        search_roots.append(path.parent)
    if path.parent.parent.exists():
        search_roots.append(path.parent.parent)

    if path.suffix.lower() == ".xml":
        return path
    if path.is_dir():
        named = path / f"{path.name}.xml"
        if named.exists():
            return named
        recursive_matches = sorted(path.rglob("*.xml"))
        if len(recursive_matches) == 1:
            return recursive_matches[0]
        if recursive_matches:
            return recursive_matches[0]
    for root in search_roots:
        recursive_matches = sorted(root.rglob("*.xml"))
        if len(recursive_matches) == 1:
            return recursive_matches[0]
        if recursive_matches:
            return recursive_matches[0]
    return path.with_suffix(".xml")


def _model_ready(model_path: str) -> bool:
    xml_path = _resolve_expected_xml(model_path)
    return xml_path.exists() and xml_path.with_suffix(".bin").exists()


def _run_downloader(model_name: str, output_dir: Path, dry_run: bool) -> int:
    command = [
        "omz_downloader",
        "--name",
        model_name,
        "--output_dir",
        str(output_dir),
    ]
    if dry_run:
        print(" ".join(command))
        return 0

    return subprocess.run(command, check=False).returncode


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    if _model_ready(str(FACE_MODEL_PATH)) and _model_ready(str(GENDER_MODEL_PATH)):
        print(f"[OK] Gender models already available at {FACE_MODEL_PATH} and {GENDER_MODEL_PATH}")
        return 0

    downloader = shutil.which("omz_downloader")
    if downloader is None:
        print("[WARN] omz_downloader was not found on PATH.")
        print(f"[INFO] Expected face model: {_resolve_expected_xml(str(FACE_MODEL_PATH))}")
        print(f"[INFO] Expected gender model: {_resolve_expected_xml(str(GENDER_MODEL_PATH))}")
        print("[INFO] Install OpenVINO tools, then rerun this script.")
        return 1

    print(f"[INFO] Using omz_downloader from: {downloader}")
    output_dir.mkdir(parents=True, exist_ok=True)

    for model_name in (FACE_MODEL_NAME, GENDER_MODEL_NAME):
        print(f"[INFO] Downloading {model_name} into {output_dir}")
        code = _run_downloader(model_name, output_dir, args.dry_run)
        if code != 0:
            print(f"[ERROR] Failed to download {model_name}")
            return code

    if _model_ready(str(FACE_MODEL_PATH)) and _model_ready(str(GENDER_MODEL_PATH)):
        print(f"[OK] Gender models are ready at {FACE_MODEL_PATH} and {GENDER_MODEL_PATH}")
        return 0

    print("[WARN] Download finished but the expected XML/BIN files were not found.")
    print(f"[INFO] Face model path: {_resolve_expected_xml(str(FACE_MODEL_PATH))}")
    print(f"[INFO] Gender model path: {_resolve_expected_xml(str(GENDER_MODEL_PATH))}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
