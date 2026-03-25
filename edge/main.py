import random
import time

def get_sensor_data():
    data = {
        "water_level": round(random.uniform(0, 100), 2),
        "soil_moisture": round(random.uniform(0, 100), 2),
        "rainfall": round(random.uniform(0, 50), 2),
        "temperature": round(random.uniform(10, 35), 2),
        "humidity": round(random.uniform(30, 90), 2)
    }
    return data

while True:
    sensor_data = get_sensor_data()
    print("Sensor Data:", sensor_data)
    time.sleep(2)