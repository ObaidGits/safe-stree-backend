"""
Geolocation Module
Uses Flask web server to get browser location via HTML5 Geolocation API
"""

from flask import Flask, request, render_template
import threading
import webbrowser
import time
import logging

location_data = {}
app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='[Location] %(message)s')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/submit_location', methods=['POST'])
def submit_location():
    global location_data
    data = request.json

    location_data = {
        "latitude": data.get('latitude'),
        "longitude": data.get('longitude'),
        "accuracy": data.get('accuracy')
    }

    logging.info(f"Received location: {location_data}")
    return "OK"


def run_server():
    try:
        app.run(port=5001, host="127.0.0.1", debug=False, use_reloader=False)
    except Exception as e:
        logging.error(f"Flask server crash: {e}")


def get_browser_location(timeout_seconds=12):
    """
    Launches browser → waits for location → returns dict or None
    Fully non blocking if wrapped in background thread.
    """

    global location_data
    location_data = {}

    # Start flask in background
    threading.Thread(target=run_server, daemon=True).start()

    # Open browser silently
    try:
        webbrowser.open("http://localhost:5001")
    except Exception as e:
        logging.error(f"Browser open failed: {e}")

    # Wait for data
    start = time.time()
    while not location_data and (time.time() - start) < timeout_seconds:
        time.sleep(0.4)

    if not location_data:
        logging.warning("Location fetch timed out. Returning None.")
        return None

    return location_data
