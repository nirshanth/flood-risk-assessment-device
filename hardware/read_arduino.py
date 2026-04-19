import serial
import requests

ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)

while True:
	line = ser.readline().decode('utf-8').strip()

	if line:
		print("Received:", line)

		if line.startswith("DATA:"):
			try:
				data = line.replace("DATA:", "")
				water, distance = data.split(",")

				water = int(water)
				distance = int(distance)

				print("Parsed -> Water:", water, "Distance:", distance)

				try:
					requests.post("http://localhost:5000/update", json={
						"water": water,
						"distance": distance
					})
				except Exception as e:
					print("ERROR SENDING:", e)

				with open("data.txt", "a") as f:
					f.write(f"{water},{distance}\n")

			except:
				print("Parse error")
