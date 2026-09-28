#!/usr/bin/env python3
"""FarmOS Modbus sensor gateway — RS-485 polling + SQLite buffer + uplink sync."""
import time
import sqlite3
import logging
import sys
from pathlib import Path

from pymodbus.client import ModbusSerialClient
import requests

# --- Config (read from gateway.toml in production) ---
SERIAL_PORT = "/dev/siddh_sensors"
BAUD_RATE = 9600
SLAVE_ID = 1
POLL_INTERVAL = 30          # seconds
DB_PATH = "/var/lib/siddh/telemetry.db"
UPLINK_URL = "http://localhost:3000/api/telemetry"  # placeholder
UPLINK_INTERVAL = 300       # seconds

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("siddh_gateway")

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("""CREATE TABLE IF NOT EXISTS telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        temperature REAL, humidity REAL, ammonia REAL,
        synced INTEGER DEFAULT 0)""")
    db.commit()
    return db

def poll_sensors(client):
    """Read sensor registers via Modbus RTU. Adjust register addresses to match your hardware."""
    try:
        # Example: temperature at register 0, humidity at 1, ammonia at 2
        rr = client.read_holding_registers(0, 3, slave=SLAVE_ID)
        if rr.isError():
            log.warning("Modbus read error: %s", rr)
            return None
        temp = rr.registers[0] / 10.0
        hum  = rr.registers[1] / 10.0
        nh3  = rr.registers[2] / 100.0
        return (temp, hum, nh3)
    except Exception as e:
        log.error("Sensor poll failed: %s", e)
        return None

def sync_uplink(db):
    """Post unsynced rows to central server."""
    rows = db.execute(
        "SELECT id, ts, temperature, humidity, ammonia FROM telemetry WHERE synced=0 LIMIT 100"
    ).fetchall()
    if not rows:
        return
    payload = [{"ts": r[1], "temperature": r[2], "humidity": r[3], "ammonia": r[4]}
               for r in rows]
    try:
        resp = requests.post(UPLINK_URL, json=payload, timeout=10)
        if resp.ok:
            ids = tuple(r[0] for r in rows)
            db.execute(f"UPDATE telemetry SET synced=1 WHERE id IN ({','.join('?'*len(ids))})", ids)
            db.commit()
            log.info("Synced %d readings upstream", len(rows))
    except Exception as e:
        log.warning("Uplink failed (will retry): %s", e)

def main():
    db = init_db()
    client = ModbusSerialClient(
        method='rtu', port=SERIAL_PORT, baudrate=BAUD_RATE,
        bytesize=8, parity='N', stopbits=1, timeout=1, retries=3)
    if not client.connect():
        log.error("Cannot open %s — check udev symlink and dongle", SERIAL_PORT)
        sys.exit(1)
    log.info("Connected to %s", SERIAL_PORT)

    last_sync = 0
    try:
        while True:
            reading = poll_sensors(client)
            if reading:
                db.execute(
                    "INSERT INTO telemetry (ts, temperature, humidity, ammonia) VALUES (?,?,?,?)",
                    (time.time(),) + reading)
                db.commit()
                log.info("T=%.1f°C  H=%.1f%%  NH3=%.2f ppm", *reading)
            if time.time() - last_sync > UPLINK_INTERVAL:
                sync_uplink(db)
                last_sync = time.time()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log.info("Shutting down")
    finally:
        client.close()
        db.close()

if __name__ == "__main__":
    main()
