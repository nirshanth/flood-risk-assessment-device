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
        line = ser.readline().decode("utf-8", errors="ignore").strip()

        if not line:
            continue

        print("Received raw:", repr(line))

        if line.startswith("DATA:"):
            payload = line[len("DATA:"):].strip()
            parts = payload.split(",")

            print("Split parts:", parts)

            if len(parts) != 4:
                print(f"Parse error: expected 4 values but got {len(parts)}")
                continue

            try:
                water1 = int(parts[0].strip())
                water2 = int(parts[1].strip())
                water3 = int(parts[2].strip())
                distance = int(parts[3].strip())

                print(
                    f"Parsed -> Water1: {water1}, Water2: {water2}, Water3: {water3}, Distance: {distance}"
                )

                response = requests.post(
                    SERVER_URL,
                    json={
                        "water1": water1,
                        "water2": water2,
                        "water3": water3,
                        "distance": distance
                    },
                    timeout=3
                )

                print("Status:", response.status_code)
                print("Server response:", response.text)

            except ValueError as e:
                print("Parse error: values were not integers")
                print("Details:", e)

    except Exception as e:
        print("Error:", e)
        time.sleep(1)
