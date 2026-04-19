"""
Voice SOS Detection Module
Listens for help/danger keywords using speech recognition
"""

import speech_recognition as sr
import threading
import time
from collections import deque
from fuzzywuzzy import fuzz


class VoiceSOSTrigger:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.triggered = False
        self.listen_thread = None
        self.help_timestamps = deque()
        self.time_window = 5  # seconds window for checking danger phrases

        self.danger_keywords = [
            "help", "please help", "help me", "i need help", "i am in danger", "can someone help", "i'm in danger"
        ]
        self.match_threshold = 80  # fuzzy match score threshold

    def _match_danger_phrase(self, phrase):
        phrase = phrase.lower()
        match_times = []
        for keyword in self.danger_keywords:
            score = fuzz.partial_ratio(phrase, keyword)
            if score >= self.match_threshold:
                print(f"[Voice] Matched danger phrase: '{keyword}' (score: {score})")
                match_times.append(time.time())
        return match_times

    def _listen_loop(self):
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source)

        while True:
            with self.microphone as source:
                try:
                    print("[Voice] Listening...")
                    audio = self.recognizer.listen(source, timeout=7)
                    phrase = self.recognizer.recognize_google(audio)
                    print("[Voice] Heard:", phrase)

                    # Match any danger-related phrase
                    match_times = self._match_danger_phrase(phrase)
                    if match_times:
                        self.help_timestamps.extend(match_times)

                    # Clean old timestamps
                    current_time = time.time()
                    while self.help_timestamps and (current_time - self.help_timestamps[0]) > self.time_window:
                        self.help_timestamps.popleft()

                    # Trigger SOS if 2+ matching danger phrases in time window
                    if len(self.help_timestamps) >= 2:
                        print("[Voice SOS] Triggered by speech!")
                        self.triggered = True
                        self.help_timestamps.clear()

                except sr.WaitTimeoutError:
                    print("[Voice] Listening timed out.")
                    continue
                except sr.UnknownValueError:
                    print("[Voice] Could not understand audio.")
                    continue
                except sr.RequestError as e:
                    print(f"[Voice Error] Could not request results; {e}")
                    continue

    def start_listening(self):
        if self.listen_thread is None:
            self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listen_thread.start()

    def check_triggered(self):
        if self.triggered:
            self.triggered = False
            return True
        return False
