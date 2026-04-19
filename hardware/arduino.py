import serial
import requests
import time

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 115200
SERVER_URL = "http://127.0.0.1:5000/update"

ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
time.sleep(2)

while True:
    try:
        line = ser.readline().decode("utf-8").strip()

        if not line:
            continue

        print("Received:", line)

        if line.startswith("DATA:"):
            try:
                payload = line.replace("DATA:", "")
                water, distance = payload.split(",")

                water = int(water)
                distance = int(distance)

                print(f"Parsed -> Water: {water}, Distance: {distance}")

                response = requests.post(
                    SERVER_URL,
                    json={"water": water, "distance": distance},
                    timeout=3
                )
                print("Server response:", response.text)

            except ValueError:
                print("Parse error: invalid DATA format")

    except Exception as e:
        print("Error:", e)
        time.sleep(1)
