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

import requests
import os
from dotenv import load_dotenv
from location_cache import get_last_location

# Load environment variables from .env file
load_dotenv()

# API Configuration
CCTV_INTERNAL_ENDPOINT = os.environ.get("CCTV_INTERNAL_ENDPOINT", "")
CCTV_INTERNAL_SERVICE_TOKEN = os.environ.get("CCTV_INTERNAL_SERVICE_TOKEN")
CCTV_INTERNAL_SERVICE_NAME = os.environ.get("CCTV_INTERNAL_SERVICE_NAME", "backend_ml")


def send_sos_to_cctv_route(image_path=None):
    """
    Send SOS alert to backend with image and location.
    Uses only internal service token auth.
    """
    if not CCTV_INTERNAL_ENDPOINT or not CCTV_INTERNAL_SERVICE_TOKEN:
        print(
            "[AUTH ERROR] Internal service auth is required. "
            "Set CCTV_INTERNAL_ENDPOINT + CCTV_INTERNAL_SERVICE_TOKEN."
        )
        return False

    endpoint = CCTV_INTERNAL_ENDPOINT
    headers = {
        "X-Internal-Service-Token": CCTV_INTERNAL_SERVICE_TOKEN,
        "X-Internal-Service-Name": CCTV_INTERNAL_SERVICE_NAME,
    }
    auth_mode = "internal-token"

    location = get_last_location()
    if not location:
        print("[Location Error] No cached location found.")
        return False

    data = {
        "latitude": str(location["latitude"]),
        "longitude": str(location["longitude"]),
        "accuracy": str(location.get("accuracy", 0)),
    }

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
        response = submit_request(endpoint, headers)

        if response.status_code == 201:
            print("[SUCCESS] SOS Alert submitted via CCTV route with image.")
            return True
        elif response.status_code == 401:
            print(f"[AUTH ERROR] Missing credentials for {auth_mode}.")
            return False
        elif response.status_code == 403:
            print(f"[AUTH ERROR] Credentials rejected for {auth_mode}.")
            return False
        elif response.status_code == 429:
            print("[RATE LIMIT] Too many SOS alerts. Please wait.")
            return False
        else:
            print(
                f"[ERROR] Failed to submit SOS. "
                f"Status: {response.status_code}, Response: {response.text}"
            )
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
