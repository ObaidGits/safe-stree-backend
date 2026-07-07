# import requests
# from location_cache import get_last_location

# API_URL = "http://localhost:5001/api/v1/cctv"      # <-- keep same as old
# AUTH_TOKEN = ""           # <-- support added


# def send_sos_to_cctv_route():
#     """
#     SAFE — Non-Blocking (when called via thread)
#     Includes timeout + failure safety
#     """

#     location = get_last_location()

#     payload = {
#         "type": "sos_alert",
#         "source": "backend_ml",
#     }

#     if location:
#         payload["latitude"] = location["latitude"]
#         payload["longitude"] = location["longitude"]
#         payload["accuracy"] = location["accuracy"]
#     else:
#         print("[WARN] No cached location. Sending SOS without location.")

#     headers = {
#         "Content-Type": "application/json"
#     }

#     if AUTH_TOKEN:
#         headers["Authorization"] = f"Bearer {AUTH_TOKEN}"

#     try:
#         res = requests.post(API_URL, json=payload, headers=headers, timeout=6)

#         if res.status_code == 200 or res.status_code == 201:
#             print("[API] SOS delivered successfully 👍")
#         else:
#             print(f"[API ERROR] Dashboard responded with {res.status_code}")
#             print(res.text)

#     except requests.Timeout:
#         print("[API ERROR] Dashboard request timed out ⏳")

#     except Exception as e:
#         print(f"[API ERROR] Failed sending SOS: {e}")

# import requests
# import os
# from location_cache import get_last_location

# CCTV_SOS_ENDPOINT = "http://localhost:8000/api/v1/cctv"
# # CCTV_SOS_ENDPOINT = "https://safe-stree-web-backend.onrender.com/api/v1/cctv"

# def send_sos_to_cctv_route():
#     location = get_last_location()
#     if not location:
#         print("[Location Error] No cached location found.")
#         return

#     data = {
#         "latitude": str(location["latitude"]),
#         "longitude": str(location["longitude"]),
#         "accuracy": str(location.get("accuracy", 0)),
#     }

#     image_path = os.path.join(os.path.dirname(__file__), "sos_alert.jpg")
#     if not os.path.isfile(image_path):
#         print("[Image Error] sos_alert.jpg not found.")
#         return

#     # Explicit filename + mimetype so Multer recognizes valid image
#     files = {
#         "sos_img": (
#             "sos_alert.jpg",
#             open(image_path, "rb"),
#             "image/jpeg"
#         )
#     }

#     try:
#         response = requests.post(
#             CCTV_SOS_ENDPOINT,
#             data=data,
#             files=files,
#             timeout=10
#         )

#         if response.status_code == 201:
#             print("[SUCCESS] SOS Alert submitted via CCTV route with image.")
#         else:
#             print(
#                 f"[ERROR] Failed to submit SOS. "
#                 f"Status: {response.status_code}, Response: {response.text}"
#             )

#     except requests.exceptions.RequestException as e:
#     finally:
#         files["sos_img"][1].close()

"""
Database and API Communication Module
Handles sending SOS alerts to backend with location and image data
"""

import json
import os

import requests

from config import (
    CCTV_API_KEY,
    CCTV_INTERNAL_ENDPOINT,
    CCTV_INTERNAL_SERVICE_NAME,
    CCTV_INTERNAL_SERVICE_TOKEN,
    CCTV_SOS_ENDPOINT,
)
from location_cache import get_last_location

def _serialize_metadata_value(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"))

    return str(value)


def _merge_metadata(data, metadata):
    if not metadata:
        return data

    for key, value in metadata.items():
        serialized = _serialize_metadata_value(value)
        if serialized is not None:
            data[key] = serialized

    return data


def send_sos_to_cctv_route(image_path=None, metadata=None):
    """
    Send SOS alert to backend with image and location.
    Prefers internal service token auth, with legacy API-key fallback.
    """
    auth_profiles = []

    if CCTV_INTERNAL_ENDPOINT and CCTV_INTERNAL_SERVICE_TOKEN:
        auth_profiles.append({
            "endpoint": CCTV_INTERNAL_ENDPOINT,
            "headers": {
                "X-Internal-Service-Token": CCTV_INTERNAL_SERVICE_TOKEN,
                "X-Internal-Service-Name": CCTV_INTERNAL_SERVICE_NAME,
            },
            "mode": "internal-token",
        })

    if CCTV_SOS_ENDPOINT and CCTV_API_KEY:
        auth_profiles.append({
            "endpoint": CCTV_SOS_ENDPOINT,
            "headers": {
                "X-API-Key": CCTV_API_KEY,
            },
            "mode": "legacy-api-key",
        })

    if not auth_profiles:
        print(
            "[AUTH ERROR] CCTV auth is not configured. "
            "Set CCTV_INTERNAL_ENDPOINT + CCTV_INTERNAL_SERVICE_TOKEN "
            "or CCTV_SOS_ENDPOINT + CCTV_API_KEY."
        )
        return False

    location = get_last_location()
    if not location:
        print("[Location Error] No cached location found.")
        return False

    data = {
        "latitude": str(location["latitude"]),
        "longitude": str(location["longitude"]),
        "accuracy": str(location.get("accuracy", 0)),
    }
    _merge_metadata(data, metadata)

    image_path = image_path or os.path.join(os.path.dirname(__file__), "sos_alert.jpg")
    if not os.path.isfile(image_path):
        print(f"[Image Error] Image not found at path: {image_path}")
        return False

    def submit_request(target_endpoint, target_headers):
        with open(image_path, "rb") as img:
            files = {
                "sos_img": (
                    "sos_alert.jpg",
                    img,
                    "image/jpeg"
                )
            }

            return requests.post(
                target_endpoint,
                data=data,
                files=files,
                headers=target_headers,
                timeout=10
            )

    try:
        last_error = None

        for profile in auth_profiles:
            response = submit_request(profile["endpoint"], profile["headers"])

            if 200 <= response.status_code < 300:
                print(f"[SUCCESS] SOS Alert submitted via CCTV route ({profile['mode']}).")
                return True

            if response.status_code in {401, 403}:
                print(
                    f"[AUTH ERROR] CCTV auth rejected for {profile['mode']}. "
                    "Trying next configured route if available."
                )
                last_error = response
                continue

            if response.status_code == 429:
                print("[RATE LIMIT] Too many SOS alerts. Please wait.")
                return False

            print(
                f"[ERROR] Failed to submit SOS via {profile['mode']}. "
                f"Status: {response.status_code}, Response: {response.text}"
            )
            last_error = response

        if last_error is not None:
            print("[ERROR] All configured CCTV routes failed.")
        return False

    except requests.exceptions.Timeout:
        print("[Request Error] Connection timed out.")
        return False
    except requests.exceptions.ConnectionError:
        print("[Request Error] Could not connect to backend server.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"[Request Error] {e}")
        return False
