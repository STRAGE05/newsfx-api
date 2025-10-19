from flask import Flask, request, jsonify
import cloudscraper, os, json, time, logging, traceback
from urllib.parse import urlencode

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def make_scraper():
    return cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
    )

scraper = make_scraper()

FF_BASE = os.environ.get('FF_GRAPH_BASE', 'https://www.forexfactory.com/calendar/graph')

COMMON_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.forexfactory.com/calendar',
    'X-Requested-With': 'XMLHttpRequest',
    'Connection': 'keep-alive',
}

def fetch_ff_graph(event_id: str) -> dict:
    url = f"{FF_BASE}?{urlencode({'do': 'flex', 'eventid': event_id})}"
    attempts = []

    for i in range(3):
        s = scraper if i == 0 else make_scraper()
        r = s.get(url, headers=COMMON_HEADERS, timeout=20)
        status = r.status_code
        text = r.text or ''
        snippet = text[:200]
        logging.info(f"[FF] attempt={i+1} status={status} len={len(text)} sample={snippet!r}")

        if status == 200:
            try:
                return r.json()
            except Exception as e:
                t = text.lstrip()
                if t.startswith(\")]}',\"):  # іноді API префіксує JSON
                    t = t[5:]
                try:
                    return json.loads(t)
                except Exception:
                    logging.warning(f\"[FF] JSON parse failed: {e}\")
                    attempts.append((status, 'json-parse-failed'))
                    continue

        if status in (403, 503) or 'Just a moment' in snippet or '__cf_chl_' in snippet:
            time.sleep(1.0 + i * 0.5)
            attempts.append((status, 'cf-challenge'))
            continue

        attempts.append((status, snippet))
        break

    raise RuntimeError(f\"FF fetch failed after retries: {attempts}\")

@app.after_request
def add_cors(resp):
    origin = request.headers.get('Origin') or '*'
    resp.headers['Access-Control-Allow-Origin'] = origin
    resp.headers['Vary'] = 'Origin'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Requested-With'
    return resp

@app.route('/api', methods=['GET', 'OPTIONS'])
def api():
    if request.method == 'OPTIONS':
        return ('', 204)

    event_id = (request.args.get('eventId') or '').strip()
    if not event_id or not event_id.isdigit():
        return jsonify({'error': 'eventId parameter is required and must be digits'}), 400

    try:
        data = fetch_ff_graph(event_id)
        events = (data or {}).get('data', {}).get('events', [])
        if not isinstance(events, list) or len(events) == 0:
            return jsonify({'labels': [], 'actualData': [], 'forecastData': []}), 200

        labels = []
        actual_data = []
        forecast_data = []
        for p in events:
            # dateline у секундах -> мс
            ts = p.get('dateline') or p.get('date') or 0
            try:
                ts = int(ts) * 1000
            except Exception:
                ts = 0
            labels.append(ts)
            actual_data.append(p.get('actual'))
            forecast_data.append(p.get('forecast'))

        return jsonify({'labels': labels, 'actualData': actual_data, 'forecastData': forecast_data}), 200

    except Exception as e:
        logging.error(\"[API] error: %s\\n%s\", str(e), traceback.format_exc())
        return jsonify({'error': 'Upstream fetch failed', 'details': str(e)}), 502

if __name__ == '__main__':
    app.run()
