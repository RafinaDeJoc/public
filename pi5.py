#!/usr/bin/env python3

import time
import json
import logging
import paho.mqtt.client as mqtt
from gpiozero import LED
import requests

HA_URL = "http://192.168.1.101:8123"
HA_TOKEN = "<TOKEN>"
TEMP_ENTITY = "sensor.sonoff_snzb_02dr2_homerseklet"
THRESHOLD_L = 26.0
THRESHOLD_H = 27.0

# --- Beállítások ---
GPIO_PIN = 17

MQTT_BROKER = "192.168.1.101"
MQTT_PORT = 1883
MQTT_USERNAME = "pi5user"
MQTT_PASSWORD = "<PASSWORD>"

DEVICE_ID = "pi5_gpio17"
COMMAND_TOPIC = f"ha/{DEVICE_ID}/set"
STATE_TOPIC = f"ha/{DEVICE_ID}/state"
AVAILABILITY_TOPIC = f"ha/{DEVICE_ID}/availability"
DISCOVERY_TOPIC = f"homeassistant/switch/{DEVICE_ID}/config"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("space_gpio")

pin = LED(GPIO_PIN)


def get_current_temperature():
    try:
        resp = requests.get(
            f"{HA_URL}/api/states/{TEMP_ENTITY}",
            headers={"Authorization": f"Bearer {HA_TOKEN}"},
            timeout=5,
        )
        resp.raise_for_status()
        return float(resp.json()["state"])
    except Exception as e:
        log.warning("Nem sikerült lekérdezni a hőmérsékletet indulásnál: %s", e)
        return None


def turn_on_switch():
    pin.on()
    log.info("GPIO%d bekapcsolva biztonsági okból (indulási hőmérséklet-ellenőrzés)", GPIO_PIN)


def startup_safety_check():

    temp = get_current_temperature()
    if temp is None:
        log.warning("Hőmérséklet ismeretlen indulásnál — biztonsági okból bekapcsolom a switchet")
        return
    if temp < THRESHOLD_L or temp > THRESHOLD_H:
        log.info("Indulási hőmérséklet %s°C < %s°C küszöb — switch bekapcsolása")
        turn_on_switch()
    else:
        log.info("Indulási hőmérséklet %s°C — küszöb felett, nincs teendő", temp)


def publish_state(client):
    state = "ON" if pin.is_lit else "OFF"
    client.publish(STATE_TOPIC, state, retain=True)
    log.info("Állapot publikálva: %s", state)
    log.info("Aktuális hőmérséklet: %s", get_current_temperature())


def publish_discovery(client):
    payload = {
        "name": "Pi5 GPIO17",
        "unique_id": DEVICE_ID,
        "command_topic": COMMAND_TOPIC,
        "state_topic": STATE_TOPIC,
        "availability_topic": AVAILABILITY_TOPIC,
        "payload_on": "ON",
        "payload_off": "OFF",
        "state_on": "ON",
        "state_off": "OFF",
        "device": {
            "identifiers": [DEVICE_ID],
            "name": "Raspberry Pi 5",
            "manufacturer": "Raspberry Pi Foundation",
            "model": "Raspberry Pi 5",
        },
    }
    client.publish(DISCOVERY_TOPIC, json.dumps(payload), retain=True)
    log.info("Discovery config elküldve.")


def on_connect(client, userdata, flags, reason_code, properties=None):
    log.info("Csatlakozva a brokerhez (kód: %s)", reason_code)
    client.publish(AVAILABILITY_TOPIC, "online", retain=True)
    publish_discovery(client)
    client.subscribe(COMMAND_TOPIC)
    publish_state(client)


def on_message(client, userdata, msg):
    payload = msg.payload.decode().strip().upper()
    log.info("Parancs érkezett: %s -> %s", msg.topic, payload)

    if payload == "ON":
        pin.on()
        print(f"GPIO{GPIO_PIN} magas (3,3V)")
    elif payload == "OFF":
        pin.off()
        print(f"GPIO{GPIO_PIN} alacsony (0V)")
    else:
        log.warning("Ismeretlen payload: %s", payload)
        return

    publish_state(client)


def main():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=DEVICE_ID,
        protocol=mqtt.MQTTv311,
    )
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.will_set(AVAILABILITY_TOPIC, "offline", retain=True)

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Várakozás a HA parancsaira. Minden parancs GPIO{GPIO_PIN}-et kapcsolja.")
    print("Kilépés: Ctrl+C")

    try:
        while True:
            try:
                client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
                client.loop_forever()
            except Exception as e:
                log.error("Kapcsolódási hiba: %s - újrapróbálkozás 5mp múlva", e)
                time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        pin.off()
        pin.close()
        print("\nKilépés, GPIO felszabadítva.")


if __name__ == "__main__":
    startup_safety_check()
    main()

