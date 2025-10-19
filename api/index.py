from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import logging
import traceback
import re

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Словник для зіставлення подій з FF на URL-шляхи Investing.com
# Це найважливіша частина! Вам потрібно буде поступово її наповнювати.
EVENT_TO_INVESTING_MAP = {
    'non-farm employment change': 'economic-calendar/non-farm-payrolls-225',
    'unemployment rate': 'economic-calendar/unemployment-rate-300',
    'cpi m/m': 'economic-calendar/cpi-733',
    'core cpi m/m': 'economic-calendar/core-cpi-736',
    'gdp': 'economic-calendar/gdp-442',
    'retail sales m/m': 'economic-calendar/retail-sales-256',
    'prelim uom inflation expectations': 'economic-calendar/michigan-inflation-expectations-1052',
    'ism manufacturing pmi': 'economic-calendar/ism-manufacturing-pmi-173',
    'federal funds rate': 'economic-calendar/fed-interest-rate-decision-168'
}

def find_investing_path(event_title):
    title_lower = event_title.lower()
    for key, path in EVENT_TO_INVESTING_MAP.items():
        if key in title_lower:
            return path
    return None

def fetch_investing_history(path):
    main_url = f"https://www.investing.com/{path}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml,q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    # 1. Робимо перший запит, щоб отримати ID для AJAX-запиту
    response = requests.get(main_url, headers=headers, timeout=15)
    response.raise_for_status()
    
    # Шукаємо ID на сторінці
    match = re.search(r'data-sml-id="(\d+)"', response.text)
    if not match:
        raise ValueError("Could not find smlId on the page")
    sml_id = match.group(1)
    
    # 2. Робимо другий POST-запит до "прихованого" API
    ajax_url = f"https://www.investing.com/events/show-more-historical-data"
    ajax_headers = {**headers, 'X-Requested-With': 'XMLHttpRequest'}
    payload = {
        'eventID': sml_id,
        'timeZone': '88', # UTC
        'smlID': sml_id,
        'limit': '150' # Кількість історичних точок
    }
    
    history_response = requests.post(ajax_url, data=payload, headers=ajax_headers, timeout=15)
    history_response.raise_for_status()
    
    # 3. Парсимо HTML-таблицю, яку повернув сервер
    soup = BeautifulSoup(history_response.text, 'html.parser')
    rows = soup.find_all('tr')
    
    labels = []
    actual_data = []
    forecast_data = []

    for row in reversed(rows): # Йдемо у зворотному порядку, щоб дати були від старих до нових
        cols = row.find_all('td')
        if len(cols) >= 4:
            # Дата у форматі Unix timestamp
            date_ts = cols[0].get('data-timestamp')
            actual = cols[1].text.strip()
            forecast = cols[2].text.strip()

            if date_ts:
                labels.append(int(date_ts) * 1000) # Перетворюємо в мілісекунди
                actual_data.append(actual)
                forecast_data.append(forecast)

    return {"labels": labels, "actualData": actual_data, "forecastData": forecast_data}

@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp

@app.route('/api', methods=['GET'])
def api():
    event_title = request.args.get('eventTitle', '')
    event_currency = request.args.get('eventCurrency', '')

    if not event_title:
        return jsonify({"error": "eventTitle is required"}), 400

    # Шукаємо шлях до сторінки Investing.com у нашому словнику
    investing_path = find_investing_path(event_title)
    if not investing_path:
        logging.warning(f"No Investing.com mapping for: '{event_title}'")
        return jsonify({"error": f"Historical data mapping not found for this event."}), 404
    
    try:
        data = fetch_investing_history(investing_path)
        return jsonify(data)
    except Exception as e:
        logging.error(f"Failed to parse {investing_path}: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Failed to fetch or parse data from Investing.com", "details": str(e)}), 502