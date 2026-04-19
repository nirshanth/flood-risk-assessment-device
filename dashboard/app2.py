from flask import Flask, jsonify, request, redirect, session, render_template_string
import sqlite3
from datetime import datetime
import requests

app = Flask(__name__)
app.secret_key = "secret123"

USERNAME = "admin"
PASSWORD = "1234"
DB_NAME = "flood_data.db"

# --------------------------
# Database helpers
# --------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            water INTEGER NOT NULL,
            distance INTEGER NOT NULL,
            rain TEXT NOT NULL,
            risk TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def calculate_rain_status(water: int) -> str:
    return "Rain Detected" if water < 500 else "No Rain"

def calculate_risk(water: int, distance: int) -> str:
    if water < 300 or distance < 80:
        return "High"
    elif water < 500 or distance < 150:
        return "Medium"
    return "Low"

def insert_reading(water: int, distance: int):
    rain = calculate_rain_status(water)
    risk = calculate_risk(water, distance)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO readings (timestamp, water, distance, rain, risk)
        VALUES (?, ?, ?, ?, ?)
    """, (timestamp, water, distance, rain, risk))
    conn.commit()
    conn.close()

def get_latest_reading():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, water, distance, rain, risk
        FROM readings
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "timestamp": row[0],
            "water": row[1],
            "distance": row[2],
            "rain": row[3],
            "risk": row[4]
        }

    return {
        "timestamp": "--",
        "water": "--",
        "distance": "--",
        "rain": "Unknown",
        "risk": "Unknown"
    }

def get_recent_readings(limit=20):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, water, distance, risk
        FROM readings
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    rows.reverse()
    return [
        {
            "timestamp": row[0],
            "water": row[1],
            "distance": row[2],
            "risk": row[3]
        }
        for row in rows
    ]

# --------------------------
# Weather helpers
# --------------------------
def geocode_location(location):
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": location,
        "count": 1,
        "language": "en",
        "format": "json"
    }

    response = requests.get(url, params=params, timeout=5)
    data = response.json()

    results = data.get("results")
    if not results:
        return None

    result = results[0]
    display_name = result["name"]
    if result.get("admin1"):
        display_name += f", {result['admin1']}"
    if result.get("country"):
        display_name += f", {result['country']}"

    return {
        "name": display_name,
        "latitude": result["latitude"],
        "longitude": result["longitude"]
    }

def get_weekly_weather(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": 7
    }

    response = requests.get(url, params=params, timeout=5)
    data = response.json()
    daily = data.get("daily", {})

    dates = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])
    rain = daily.get("precipitation_sum", [])
    rain_prob = daily.get("precipitation_probability_max", [])
    weather_codes = daily.get("weather_code", [])

    forecast = []
    for i in range(len(dates)):
        forecast.append({
            "date": dates[i],
            "max_temp": max_temps[i] if i < len(max_temps) else None,
            "min_temp": min_temps[i] if i < len(min_temps) else None,
            "rain_mm": rain[i] if i < len(rain) else 0,
            "rain_probability": rain_prob[i] if i < len(rain_prob) else 0,
            "weather_code": weather_codes[i] if i < len(weather_codes) else None
        })

    return forecast

def weather_label_from_code(code):
    if code is None:
        return "Unknown"
    if code == 0:
        return "Clear"
    if code in [1, 2, 3]:
        return "Cloudy"
    if code in [45, 48]:
        return "Fog"
    if code in [51, 53, 55, 56, 57]:
        return "Drizzle"
    if code in [61, 63, 65, 66, 67, 80, 81, 82]:
        return "Rain"
    if code in [71, 73, 75, 77, 85, 86]:
        return "Snow"
    if code in [95, 96, 99]:
        return "Thunderstorm"
    return "Mixed"

# --------------------------
# HTML templates
# --------------------------
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Flood Monitoring Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a, #1e293b);
            color: white;
        }
        .login-box {
            width: 100%;
            max-width: 380px;
            background: rgba(255,255,255,0.08);
            backdrop-filter: blur(10px);
            padding: 30px;
            border-radius: 18px;
            box-shadow: 0 10px 35px rgba(0,0,0,0.3);
        }
        h2 {
            margin-top: 0;
            text-align: center;
            margin-bottom: 24px;
        }
        input {
            width: 100%;
            padding: 14px;
            margin-bottom: 14px;
            border: none;
            border-radius: 10px;
            outline: none;
            font-size: 15px;
        }
        button {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 10px;
            background: #2563eb;
            color: white;
            font-size: 15px;
            font-weight: bold;
            cursor: pointer;
        }
        button:hover {
            background: #1d4ed8;
        }
        .error {
            color: #fca5a5;
            text-align: center;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>Flood Monitoring Login</h2>
        <form method="post">
            <input name="username" placeholder="Username" required>
            <input name="password" type="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Flood Monitoring Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a, #111827);
            color: white;
        }

        .navbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 32px;
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            position: sticky;
            top: 0;
            z-index: 10;
        }

        .navbar h1 {
            margin: 0;
            font-size: 28px;
        }

        .logout-btn {
            text-decoration: none;
            background: #ef4444;
            color: white;
            padding: 10px 16px;
            border-radius: 10px;
            font-weight: bold;
        }

        .container {
            max-width: 1200px;
            margin: 30px auto;
            padding: 0 20px 40px;
        }

        .top-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 28px;
        }

        .card {
            background: rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.25);
        }

        .card-title {
            font-size: 14px;
            color: #cbd5e1;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .card-value {
            font-size: 32px;
            font-weight: bold;
        }

        .risk-low { color: #22c55e; }
        .risk-medium { color: #f59e0b; }
        .risk-high { color: #ef4444; }

        .chart-card,
        .weather-card {
            background: rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.25);
            margin-top: 28px;
        }

        .chart-header,
        .weather-header {
            margin-bottom: 20px;
        }

        .chart-header h2,
        .weather-header h2 {
            margin: 0 0 6px 0;
        }

        .chart-header p,
        .weather-header p {
            margin: 0;
            color: #cbd5e1;
        }

        .footer-note {
            margin-top: 16px;
            color: #94a3b8;
            font-size: 14px;
        }

        canvas {
            background: white;
            border-radius: 12px;
            padding: 10px;
        }

        .search-row {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }

        .search-row input {
            flex: 1;
            min-width: 220px;
            padding: 14px;
            border: none;
            border-radius: 10px;
            outline: none;
            font-size: 15px;
        }

        .search-row button {
            padding: 14px 18px;
            border: none;
            border-radius: 10px;
            background: #2563eb;
            color: white;
            font-weight: bold;
            cursor: pointer;
        }

        .search-row button:hover {
            background: #1d4ed8;
        }

        .forecast-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 16px;
        }

        .forecast-item {
            background: rgba(255,255,255,0.06);
            border-radius: 14px;
            padding: 16px;
        }

        .forecast-date {
            font-size: 15px;
            font-weight: bold;
            margin-bottom: 10px;
        }

        .forecast-line {
            font-size: 14px;
            color: #dbeafe;
            margin-bottom: 6px;
        }

        .muted {
            color: #94a3b8;
        }

        .error-text {
            color: #fca5a5;
            margin-top: 10px;
        }

        @media (max-width: 640px) {
            .navbar {
                padding: 16px 18px;
            }

            .navbar h1 {
                font-size: 20px;
            }

            .card-value {
                font-size: 24px;
            }
        }
    </style>
</head>
<body>
    <div class="navbar">
        <h1>Flood Monitoring Dashboard</h1>
        <a class="logout-btn" href="/logout">Logout</a>
    </div>

    <div class="container">
        <div class="top-info">
            <div class="card">
                <div class="card-title">Water Sensor</div>
                <div class="card-value" id="water">--</div>
            </div>

            <div class="card">
                <div class="card-title">Distance</div>
                <div class="card-value" id="distance">-- mm</div>
            </div>

            <div class="card">
                <div class="card-title">Rain Status</div>
                <div class="card-value" id="rain">--</div>
            </div>

            <div class="card">
                <div class="card-title">Risk Level</div>
                <div class="card-value" id="risk">--</div>
            </div>
        </div>

        <div class="chart-card">
            <div class="chart-header">
                <h2>Live Sensor History</h2>
                <p>Latest update: <span id="timestamp">--</span></p>
            </div>
            <canvas id="sensorChart" height="110"></canvas>
            <div class="footer-note">Chart updates automatically every 2 seconds.</div>
        </div>

        <div class="weather-card">
            <div class="weather-header">
                <h2>Weekly Weather Forecast</h2>
                <p>Enter a city, town, or ZIP code to view the 7-day forecast.</p>
            </div>

            <div class="search-row">
                <input type="text" id="locationInput" placeholder="Enter location (example: New Brunswick, NJ or 08854)">
                <button onclick="loadWeeklyWeather()">Get Weekly Weather</button>
            </div>

            <p class="muted">Forecast location: <span id="weatherLocation">None selected</span></p>
            <div id="weatherError" class="error-text"></div>
            <div id="forecastContainer" class="forecast-grid"></div>
        </div>
    </div>

    <script>
        let sensorChart;

        async function loadChartData() {
            const response = await fetch('/history');
            const history = await response.json();

            const labels = history.map(item => item.timestamp.split(' ')[1]);
            const waterData = history.map(item => item.water);
            const distanceData = history.map(item => item.distance);

            const ctx = document.getElementById('sensorChart').getContext('2d');

            if (sensorChart) {
                sensorChart.data.labels = labels;
                sensorChart.data.datasets[0].data = waterData;
                sensorChart.data.datasets[1].data = distanceData;
                sensorChart.update();
            } else {
                sensorChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Water Sensor',
                                data: waterData,
                                borderWidth: 2,
                                tension: 0.3
                            },
                            {
                                label: 'Distance (mm)',
                                data: distanceData,
                                borderWidth: 2,
                                tension: 0.3
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true
                    }
                });
            }
        }

        async function loadLatestData() {
            const response = await fetch('/data');
            const data = await response.json();

            document.getElementById('water').textContent = data.water;
            document.getElementById('distance').textContent = data.distance + ' mm';
            document.getElementById('rain').textContent = data.rain;

            const riskElement = document.getElementById('risk');
            riskElement.textContent = data.risk;
            riskElement.className = 'card-value';

            if (data.risk === 'Low') riskElement.classList.add('risk-low');
            else if (data.risk === 'Medium') riskElement.classList.add('risk-medium');
            else if (data.risk === 'High') riskElement.classList.add('risk-high');

            document.getElementById('timestamp').textContent = data.timestamp;
        }

        async function refreshDashboard() {
            await loadLatestData();
            await loadChartData();
        }

        function formatDate(dateString) {
            const date = new Date(dateString + "T00:00:00");
            return date.toLocaleDateString([], {
                weekday: 'short',
                month: 'short',
                day: 'numeric'
            });
        }

        async function loadWeeklyWeather() {
            const location = document.getElementById('locationInput').value.trim();
            const container = document.getElementById('forecastContainer');
            const locationLabel = document.getElementById('weatherLocation');
            const errorBox = document.getElementById('weatherError');

            container.innerHTML = "";
            errorBox.textContent = "";

            if (!location) {
                errorBox.textContent = "Please enter a location.";
                return;
            }

            try {
                const response = await fetch(`/weekly-weather?location=${encodeURIComponent(location)}`);
                const data = await response.json();

                if (!response.ok) {
                    errorBox.textContent = data.error || "Unable to load weather.";
                    return;
                }

                locationLabel.textContent = data.location;

                data.forecast.forEach(day => {
                    const card = document.createElement('div');
                    card.className = 'forecast-item';
                    card.innerHTML = `
                        <div class="forecast-date">${formatDate(day.date)}</div>
                        <div class="forecast-line"><strong>${day.summary}</strong></div>
                        <div class="forecast-line">High: ${day.max_temp}°C</div>
                        <div class="forecast-line">Low: ${day.min_temp}°C</div>
                        <div class="forecast-line">Rain: ${day.rain_mm} mm</div>
                        <div class="forecast-line">Rain Chance: ${day.rain_probability}%</div>
                    `;
                    container.appendChild(card);
                });
            } catch (error) {
                errorBox.textContent = "Error loading weekly weather.";
                console.log(error);
            }
        }

        refreshDashboard();
        setInterval(refreshDashboard, 2000);
    </script>
</body>
</html>
"""

# --------------------------
# Routes
# --------------------------
@app.route("/")
def root():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = request.form.get("username")
        pwd = request.form.get("password")

        if user == USERNAME and pwd == PASSWORD:
            session["logged_in"] = True
            return redirect("/dashboard")
        else:
            error = "Invalid login"

    return render_template_string(LOGIN_HTML, error=error)

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect("/login")
    return render_template_string(DASHBOARD_HTML)

@app.route("/data")
def data():
    if not session.get("logged_in"):
        return redirect("/login")
    return jsonify(get_latest_reading())

@app.route("/history")
def history():
    if not session.get("logged_in"):
        return redirect("/login")
    return jsonify(get_recent_readings(20))

@app.route("/update", methods=["POST"])
def update():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data received"}), 400

    try:
        water = int(data["water"])
        distance = int(data["distance"])
        insert_reading(water, distance)
        return jsonify({"message": "Reading stored successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/weekly-weather")
def weekly_weather():
    if not session.get("logged_in"):
        return redirect("/login")

    location = request.args.get("location", "").strip()
    if not location:
        return jsonify({"error": "Location is required"}), 400

    try:
        geo = geocode_location(location)
        if not geo:
            return jsonify({"error": "Location not found"}), 404

        forecast = get_weekly_weather(geo["latitude"], geo["longitude"])

        for day in forecast:
            day["summary"] = weather_label_from_code(day.get("weather_code"))

        return jsonify({
            "location": geo["name"],
            "forecast": forecast
        })
    except Exception as e:
        return jsonify({"error": f"Weather lookup failed: {str(e)}"}), 500

# --------------------------
# Start app
# --------------------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
