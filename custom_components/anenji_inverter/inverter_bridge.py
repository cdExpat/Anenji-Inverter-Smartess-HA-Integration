
import threading
import struct
import time
import json
import logging
from datetime import datetime

# Home Assistant Logger
_LOGGER = logging.getLogger(__name__)

# Lock objects for thread safety
modbus_lock = threading.Lock()
energy_lock = threading.Lock()

# Persistent energy accumulator defaults
energy_data = {
    "total_pv_kwh": 0.0,
    "total_grid_input_kwh": 0.0,
    "total_load_kwh": 0.0,
    "total_battery_charge_kwh": 0.0,
    "total_battery_discharge_kwh": 0.0,
}

STATUS_MAP = {
    0: "Initialization",
    1: "Standby",
    2: "Active",
    3: "Fault",
    4: "Flash/Update",
}

BATTERY_TYPE_MAP = {
    0: "AGM",
    1: "FLD",
    2: "USR",
    3: "USE",
    4: "LI2",
    6: "LI4",
    8: "LIb",
}

def to_signed(val):
    """Converts 16-bit unsigned integer to signed integer."""
    return val - 65536 if val > 32767 else val

def build_read_packet(start_reg, count):
    """Builds Modbus RTU read holding registers packet (Function Code 03)."""
    p = bytearray([0x01, 0x03, start_reg >> 8, start_reg & 0xFF, count >> 8, count & 0xFF])
    crc = 0xFFFF
    for b in p:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    p.append(crc & 0xFF)
    p.append(crc >> 8)
    return p

def flush_buffer(conn):
    """Flushes stale bytes from the socket rx buffer."""
    conn.settimeout(0.01)
    try:
        while conn.recv(1024):
            pass
    except Exception:
        pass
    conn.settimeout(2.5)

def read_modbus_response(conn):
    """Reads and validates Modbus response bytes."""
    try:
        header = conn.recv(3)
        if len(header) < 3:
            return None
        byte_cnt = header[2]
        payload = b''
        while len(payload) < byte_cnt + 2:
            chunk = conn.recv((byte_cnt + 2) - len(payload))
            if not chunk:
                break
            payload += chunk
        if len(payload) < byte_cnt + 2:
            return None
        vals = []
        for i in range(0, byte_cnt, 2):
            vals.append(struct.unpack('>H', payload[i:i+2])[0])
        return vals
    except Exception:
        return None

def send_dongle_redirect(stick_ip, stick_port, server_ip, server_port):
    """Sends the UDP command to re-point the Eybond stick back to our local bridge IP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        target_str = f"{server_ip}:{server_port}"
        payload = f"set>server={target_str};".encode()
        sock.sendto(payload, (stick_ip, int(stick_port)))
        _LOGGER.info("Sent UDP redirect payload to %s:%s -> %s", stick_ip, stick_port, target_str)
        sock.close()
    except Exception as e:
        _LOGGER.error("Failed to send UDP redirect: %s", e)

def publish_ha_discovery(mqtt_client, mqtt_prefix="homeassistant"):
    """Publishes MQTT discovery topics for Home Assistant entities."""
    sensors = {
        "pv_input_watt": ["PV Power", "W", "power", "measurement"],
        "pv_input_volt": ["PV Voltage", "V", "voltage", "measurement"],
        "batt_volt": ["Battery Voltage", "V", "voltage", "measurement"],
        "batt_soc": ["Battery Capacity", "%", "battery", "measurement"],
        "batt_power_watt": ["Battery Power", "W", "power", "measurement"],
        "ac_load_real_watt": ["AC Load Power", "W", "power", "measurement"],
        "grid_volt": ["Grid Voltage", "V", "voltage", "measurement"],
        "total_pv_energy_kwh": ["Total Solar Energy", "kWh", "energy", "total_increasing"],
        "total_load_kwh": ["Total Load Energy", "kWh", "energy", "total_increasing"],
        "total_battery_charge_kwh": ["Total Battery Charge Energy", "kWh", "energy", "total_increasing"],
        "total_battery_discharge_kwh": ["Total Battery Discharge Energy", "kWh", "energy", "total_increasing"]
    }
    
    for key, (name, unit, dev_class, state_class) in sensors.items():
        topic = f"{mqtt_prefix}/sensor/anenji_modbus/{key}/config"
        payload = {
            "name": f"Anenji {name}",
            "state_topic": f"anenji_inverter/{key}/state",
            "unit_of_measurement": unit,
            "device_class": dev_class,
            "state_class": state_class,
            "unique_id": f"anenji_modbus_{key}",
            "device": {
                "identifiers": ["anenji_anj_4200w_modbus"],
                "name": "Anenji Inverter (Modbus)",
                "model": "ANJ-4200W",
                "manufacturer": "Anenji"
            }
        }
        mqtt_client.publish(topic, json.dumps(payload), retain=True)

def publish_mqtt_state(mqtt_client, data_json):
    """Publishes live values to state topics."""
    for key, val in data_json.items():
        if val is not None:
            topic = f"anenji_inverter/{key}/state"
            mqtt_client.publish(topic, str(val))


def start_inverter_bridge_thread(config, mqtt_client, stop_event):
    """Main worker thread entry point spawned by __init__.py."""
    
    # Extract config values from UI config flow
    stick_ip = config.get("stick_ip", "192.168.138.2")
    stick_port = config.get("stick_port", 58899)
    server_ip = config.get("server_ip", "192.168.138.3")
    server_port = config.get("server_port", 18899)

    # Publish discovery configs once at startup
    publish_ha_discovery(mqtt_client)

    # Create local TCP listener socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Bind to 0.0.0.0 or specific interface IP
    try:
        s.bind(("0.0.0.0", int(server_port)))
        s.listen(1)
        _LOGGER.info("Inverter Bridge TCP listener started on port %s", server_port)
    except Exception as e:
        _LOGGER.error("Failed to bind TCP listener on port %s: %s", server_port, e)
        return

    consecutive_failures = 0
    last_integration_time = time.time()
    latest_data_json = {}

    while not stop_event.is_set():
        try:
            _LOGGER.info("Waiting for Inverter connection on port %s...", server_port)
            s.settimeout(5.0)  # Check stop_event every 5 seconds

            try:
                conn, addr = s.accept()
            except socket.timeout:
                if not stop_event.is_set():
                    _LOGGER.info("Connection timeout. Re-issuing UDP redirect to %s:%s...", stick_ip, stick_port)
                    send_dongle_redirect(stick_ip, stick_port, server_ip, server_port)
                continue

            conn.settimeout(5.0)
            _LOGGER.info("Inverter connected from %s:%s", addr[0], addr[1])

            # Send AT Handshake
            try:
                _LOGGER.info("Sending Wake-up Command (AT+DTUPN?)...")
                conn.send(b'AT+DTUPN?\r\n')
                reply = conn.recv(1024)
                _LOGGER.info("Dongle replied: %s", reply.decode(errors='ignore').strip())
                time.sleep(0.5)
            except Exception as e:
                _LOGGER.error("Handshake failed: %s", e)
                conn.close()
                send_dongle_redirect(stick_ip, stick_port, server_ip, server_port)
                continue

            conn.settimeout(2.5)
            consecutive_failures = 0

            # --- INNER POLLING LOOP ---
            while not stop_event.is_set():
                now = time.time()
                time_delta = now - last_integration_time
                last_integration_time = now

                with modbus_lock:
                    try:
                        flush_buffer(conn)
                        conn.send(build_read_packet(200, 40))
                        time.sleep(0.15)
                        vals = read_modbus_response(conn)

                        if vals is None:
                            consecutive_failures += 1
                            if consecutive_failures >= 5:
                                _LOGGER.warning("Max consecutive failures reached. Resetting connection...")
                                break
                        else:
                            consecutive_failures = 0

                            v_batt = round(float(vals[15]) / 10.0, 1)
                            if v_batt < 10.0:
                                v_batt = 48.0

                            v_pv = vals[19] / 10.0
                            p_pv = vals[23]
                            p_pv_btt = vals[24]
                            v_grid = vals[2] / 10.0
                            p_grid = vals[4]
                            p_load = vals[13]

                            raw_batt_current = to_signed(vals[32])
                            batt_current = raw_batt_current / 10.0
                            batt_p = int(batt_current * v_batt)

                            if 0 < time_delta < 5.0:
                                with energy_lock:
                                    if p_pv > 0:
                                        energy_data["total_pv_kwh"] += (p_pv * time_delta) / 3600000.0
                                    if p_load > 0:
                                        energy_data["total_load_kwh"] += (p_load * time_delta) / 3600000.0
                                    if batt_p > 0:
                                        energy_data["total_battery_charge_kwh"] += (batt_p * time_delta) / 3600000.0
                                    elif batt_p < 0:
                                        energy_data["total_battery_discharge_kwh"] += (abs(batt_p) * time_delta) / 3600000.0

                                    latest_data_json["total_pv_energy_kwh"] = round(energy_data["total_pv_kwh"], 4)
                                    latest_data_json["total_load_kwh"] = round(energy_data["total_load_kwh"], 4)
                                    latest_data_json["total_battery_charge_kwh"] = round(energy_data["total_battery_charge_kwh"], 4)
                                    latest_data_json["total_battery_discharge_kwh"] = round(energy_data["total_battery_discharge_kwh"], 4)

                            latest_data_json.update({
                                "grid_volt": v_grid,
                                "ac_load_real_watt": p_load,
                                "batt_volt": v_batt,
                                "batt_soc": vals[29],
                                "batt_power_watt": batt_p,
                                "pv_input_watt": p_pv,
                                "pv_input_volt": v_pv,
                            })

                            publish_mqtt_state(mqtt_client, latest_data_json)

                    except Exception as e:
                        _LOGGER.error("Error during polling loop: %s", e)
                        consecutive_failures += 1
                        if consecutive_failures >= 5:
                            break

                time.sleep(2.0)  # Polling interval

            conn.close()

        except Exception as e:
            if not stop_event.is_set():
                _LOGGER.error("Connection error: %s", e)
                time.sleep(1)
        finally:
            if not stop_event.is_set():
                send_dongle_redirect(stick_ip, stick_port, server_ip, server_port)

    s.close()
    _LOGGER.info("Inverter Bridge worker thread stopped cleanly.")
