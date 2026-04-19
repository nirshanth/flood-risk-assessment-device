from flask import Flask, jsonify, request, redirect, session

app = Flask(__name__)

app.secret_key = "secret123"

# this stores latest sensor data
latest_data = {
	"water": 0,
	"distance": 0,
	"rain": "Unknown"
}

USERNAME = "admin"
PASSWORD = "1234"

@app.route("/dashboard")
def home():
	if not session.get("logged_in"):
		return redirect("/")
	return """
	<html>
	<head>
		<title>Flood Monitoring Dashboard</title>

		<style>
			body {
				font-family: Arial;
				background: #0f172a;
				color: white;
				margin: 0;

				display: flex;
				flex-direction: column;
				align-items: center;
			}

			h1 {
				margin-top: 30px;
			}

			.container {
				display: flex;
				justify-content: center;
				align-items: center;
				gap: 30px;
				margin-top: 60px;
				flex-wrap: wrap;
			}

			.card {
				background: #1e293b;
				padding: 25px;
				border-radius: 15px;
				width: 220px;
				box-shadow: 0px 4px 15px rgba(0,0,0,0.4);
				transition: 0.3s;
				text-align: center;
			}

			.card:hover {
				transform: scale(1.05);
			}

			.title {
				font-size: 18px;
				opacity: 0.8;
			}

			.value {
				font-size: 32px;
				margin-top: 10px;
				font-weight: bold;
			}

			.logout-container {
				display: flex;
				justify-content: center;
				margin-top: 10px;
			}

			.logout-btn {
				margin-top: 20px;
				padding: 10px 20px;
				background: #ef4444;
				border: none;
				color: white;
				border-radius: 8px;
				cursor: pointer;
			}

			.logout-btn:hover {
				background: #dc2626;
			}
		</style>
	</head>
	<body>
		<h1>Flood Monitoring System<h1>
		<br>
		<div class="logout-container">
			<a href="/logout">
				<button class="logout-btn">Logout</button>
			</a>
		</div>
		<br><br>

		<div class="container">

			<div class="card">
				<div class="title">Water Level</div>
				<div class="value" id="water">--</div>
			</div>

			<div class="card">
				<div class="title">Distance</div>
				<div class="value" id="distance">-- mm</div>
			</div>

			<div class="card">
				<div class="title">Rain Status</div>
				<div class="value" id="rain">--</div>
				</div>
		</div>

		<script>
		function updateData() {
			fetch('/data?' + new Date().getTime())
				.then(response => response.json())
				.then(data => {
					document.getElementById("water").textContent = data.water;
					doucment.getElementById("distance").textContent = data.distance + " mm";
					document.getElementById("rain").textContent = data.rain;
				});
				.catch(err => console.log("ERROR:", err));
		}

		setInterval(updateData, 1000);
		</script>


	</body>
	</html>
	"""

@app.route("/logout")
def logout():
	session.pop("logged_in", None)
	return redirect("/")

@app.route("/data")
def get_data():
	return jsonify(latest_data)

@app.route("/update", methods=["POST"])
def update():
	data = request.get_json()
	print(data)

	water = data["water"]
	distance = data["distance"]

	# this is rain logic
	if water < 500:
		rain_status = "Rain Detected"
	else:
		rain_status = "No Rain"

	latest_data["water"] = water
	latest_data["distance"] = distance
	latest_data["rain"] = rain_status

	return "OK"

@app.route("/")
def root():
	return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
	if request.method  == "POST":
		user = request.form.get("username")
		pwd = request.form.get("password")

		if user == USERNAME and pwd == PASSWORD:
			session["logged_in"] = True
			return redirect("/dashboard")
		else:
			return "Invalid login"
	return """
	<html>
	<head>
		<title>Login</title>
		<style>
			body {
				background: #111;
				color: white;
				font-family: Arial;
				display: flex;
				justify-content: center;
				align-items: center;
				height: 100vh;
			}
			.login-box {
				background: #222;
				padding: 30px;
				border-radius: 10px;
				text-align: center;
			}
			input {
				padding: 10px;
				margin: 10px;
				width: 200px;
			}
			button {
				padding: 10px 20px;
				background: #00cc66;
				border: none;
				color: white;
				cursor: pointer;
			}
		</style>
	</head>
	<body>
		<div class="login-box">
			<h2>Login</h2>
			<form method="post">
				<input name="username" placeholder="Username"><br>
				<input name="password" type="password" placeholder="Password"><br>
				<button type="submit">Login</button>
			</form>
		</div>
	</body>
	</html>
	"""

if __name__ == "__main__":
	app.run(host="0.0.0.0", port=5000)

