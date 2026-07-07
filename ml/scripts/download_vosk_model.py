#!/usr/bin/env python3
"""Download and install an offline Vosk model for SafeStree.

The script keeps model downloads explicit and local. It does not fetch anything
at runtime inside the app.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import VOICE_MODEL_PATH


MODEL_MAP = {
    "en": {
        "name": "vosk-model-small-en-us-0.15",
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "target": Path("data/models/voice/vosk-model-small-en-us"),
    },
    "hi": {
        "name": "vosk-model-small-hi-0.22",
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip",
        "target": Path("data/models/voice/vosk-model-small-hi"),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a local Vosk model for SafeStree")
    parser.add_argument(
        "--language",
        choices=sorted(MODEL_MAP.keys()),
        default="en",
        help="Model language to download (default: en)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/models/voice",
        help="Directory where the Vosk model should be stored",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing model directory",
    )
    return parser.parse_args()


def _is_ready(model_dir: Path) -> bool:
    required = [
        model_dir / "am" / "final.mdl",
        model_dir / "conf" / "model.conf",
    ]
    return model_dir.exists() and model_dir.is_dir() and all(path.exists() for path in required)


def _download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:  # nosec B310
        shutil.copyfileobj(response, handle)


def _extract_zip(zip_path: Path, staging_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(staging_dir)

    candidates = sorted(
        path for path in staging_dir.iterdir() if path.is_dir() and path.name.startswith("vosk-model-")
    )
    if not candidates:
        raise FileNotFoundError("Extracted Vosk model folder not found in archive")
    return candidates[0]


def main() -> int:
    args = parse_args()
    model_spec = MODEL_MAP[args.language]
    output_dir = Path(args.output_dir)
    target_dir = output_dir / model_spec["target"].name

    if _is_ready(target_dir) and not args.force:
        print(f"[OK] Vosk model already available at {target_dir}")
        return 0

    staging_dir = output_dir / f".{target_dir.name}_download"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    zip_path = staging_dir / f"{model_spec['name']}.zip"
    print(f"[INFO] Downloading {model_spec['name']}")
    print(f"[INFO] Source: {model_spec['url']}")
    _download_file(model_spec["url"], zip_path)

    print("[INFO] Extracting archive")
    extracted_root = _extract_zip(zip_path, staging_dir)

    if target_dir.exists():
        if args.force:
            shutil.rmtree(target_dir)
        else:
            raise FileExistsError(f"Target model directory already exists: {target_dir}")

    shutil.move(str(extracted_root), str(target_dir))
    shutil.rmtree(staging_dir, ignore_errors=True)

    if _is_ready(target_dir):
        print(f"[OK] Vosk model ready at {target_dir}")
        if Path(VOICE_MODEL_PATH).resolve() != target_dir.resolve():
            print(f"[INFO] Update VOICE_MODEL_PATH to {target_dir}")
        return 0

    print("[ERROR] Vosk model download completed but required files are missing")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
