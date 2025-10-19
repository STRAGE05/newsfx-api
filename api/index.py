from flask import Flask, request, jsonify
import cloudscraper
import json
import logging
import traceback

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def make_scraper():
    # Використовуємо більш просунутий JS-вирішувач, якщо доступний
    return cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False},
        delay=10, # Додаємо невелику затримку
        interpreter='nodejs' # Спроба використати Node.js для вирішення челенджу
    )

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    event_id = request.args.get('eventId')
    if not event_id:
        return jsonify({"error": "eventId parameter is required"}), 400

    url = f"https.forexfactory.com/calendar/graph?do=flex&eventid={event_id}"
    
    # Додаємо ще більше "людських" заголовків
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-US,en;q=0.9,uk;q=0.8',
        'Referer': 'https.forexfactory.com/calendar',
        'X-Requested-With': 'XMLHttpRequest',
    }

    try:
        scraper = make_scraper()
        response = scraper.get(url, headers=headers, timeout=25)
        logging.info(f"[FF] Request for {event_id} status: {response.status_code}. Content length: {len(response.text)}")

        if response.status_code != 200:
            return jsonify({"error": "Source returned non-200 status", "status": response.status_code}), 502

        # Перевірка, чи не отримали ми HTML
        if response.text.strip().startswith('<'):
             logging.error(f"[FF] Blocked by Cloudflare. Received HTML page instead of JSON. Snippet: {response.text[:200]}")
             return jsonify({"error": "Request blocked by source (Cloudflare)"}), 503

        # Парсимо JSON
        data = response.json()
        events = data.get("data", {}).get("events", [])
        
        labels = [p.get("dateline", 0) * 1000 for p in events]
        actual_data = [p.get("actual") for p in events]
        forecast_data = [p.get("forecast") for p in events]

        return jsonify({
            "labels": labels,
            "actualData": actual_data,
            "forecastData": forecast_data
        })

    except Exception as e:
        logging.error(f"[API] Error processing {event_id}: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": "An internal error occurred", "details": str(e)}), 500