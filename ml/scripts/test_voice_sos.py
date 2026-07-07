#!/usr/bin/env python3
"""Offline smoke test for the SafeStree voice SOS pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sos_voice.voice import VoicePhraseMatcher, VoiceSOSTrigger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline voice SOS checks")
    parser.add_argument("--offline", action="store_true", help="Run without microphone or Vosk model")
    return parser.parse_args()


def run_offline_checks() -> None:
    matcher = VoicePhraseMatcher()
    positive = matcher.match("please help me")
    negative = matcher.match("good morning everyone")

    assert positive is not None, "Expected a positive emergency phrase to match"
    assert positive.label == "SOS", "Expected the SOS label"
    assert positive.confidence >= 0.9, "Expected a strong positive confidence"
    assert negative is None, "Expected a non-emergency phrase to stay unmatched"

    detector = VoiceSOSTrigger(enable_audio=False, high_confidence_threshold=1.1)
    assert detector.start_listening() is False, "Audio-disabled detector should not start"
    assert detector.process_transcript("hello there", timestamp=1000.0) is None
    assert detector.process_transcript("please help me", timestamp=1001.0) is None

    event = detector.process_transcript("please help me", timestamp=1002.0)
    assert event is not None, "Expected the second emergency hit to confirm"
    assert event["triggerType"] == "voice_sos"
    assert event["voiceMatchedPhrase"], "Expected the matched phrase to be recorded"

    single_hit_detector = VoiceSOSTrigger(
        enable_audio=False,
        confirmation_hits=3,
        high_confidence_threshold=0.85,
    )
    high_conf_event = single_hit_detector.process_transcript("i am in danger", timestamp=2000.0)
    assert high_conf_event is not None, "Expected a strong exact phrase to confirm immediately"


def main() -> int:
    parse_args()
    run_offline_checks()
    print("[OK] Offline voice SOS smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
