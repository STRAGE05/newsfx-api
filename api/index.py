from flask import Flask, request, jsonify
import cloudscraper

# Створюємо Flask-додаток
app = Flask(__name__)

# Створюємо скрейпер, який вміє обходити Cloudflare
scraper = cloudscraper.create_scraper()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    # Отримуємо eventId з параметрів запиту (напр. .../api?eventId=141471)
    event_id = request.args.get('eventId')

    if not event_id:
        return jsonify({"error": "eventId parameter is required"}), 400

    # Формуємо URL до "прихованого" API Forex Factory
    url = f"https://www.forexfactory.com/calendar/graph?do=flex&eventid={event_id}"

    try:
        # Робимо запит через cloudscraper
        response = scraper.get(url)
        print(f"Request to FF for eventId {event_id} status: {response.status_code}") # Лог для перевірки

        # Перевіряємо, чи успішний запит
        if response.status_code == 200:
            # Парсимо JSON-відповідь
            data = response.json()
            
            # Перетворюємо дані у потрібний нам формат
            events = data.get("data", {}).get("events", [])
            
            labels = [point.get("dateline") * 1000 for point in events] # Перетворюємо в мілісекунди
            actual_data = [point.get("actual") for point in events]
            forecast_data = [point.get("forecast") for point in events]

            # Повертаємо чистий JSON розширенню
            return jsonify({
                "labels": labels,
                "actualData": actual_data,
                "forecastData": forecast_data
            })
        else:
            return jsonify({"error": "Failed to fetch data from source", "status": response.status_code}), 502

    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({"error": "An internal error occurred"}), 500

# Цей код потрібен, щоб Vercel зрозумів, як запускати наш додаток
if __name__ == "__main__":
    app.run()