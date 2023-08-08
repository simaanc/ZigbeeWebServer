import pyftdi.serialext
from flask import Flask, render_template, make_response, jsonify, request
import datetime
import time
import csv
import sqlite3
import os
import pytz
import threading
import dateutil.parser
from pathlib import Path

app = Flask(__name__)

# Paths and configuration
source_path = Path(__file__).resolve()
source_dir = source_path.parent
DATA_FILE = 'data.db'
DEVICES_FILE = 'devices.db'
CSV_FILE = 'data.csv'

# Open a serial port on the second FTDI device interface (IF/2) @ 115200 baud
port = pyftdi.serialext.serial_for_url('ftdi://ftdi:232:/1', baudrate=115200)


current_value = "0"

# MQTT client setup
running = False

# Create SQLite database if it doesn't exist
if not os.path.isfile(DATA_FILE):
    conn = sqlite3.connect(DATA_FILE)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE sensor_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node TEXT,
        date_time TEXT,
        value TEXT
    )""")
    conn.commit()
    conn.close()

# Create SQLite database if it doesn't exist
if not os.path.isfile(DEVICES_FILE):
    conn = sqlite3.connect(DEVICES_FILE)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE devices_list (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node TEXT,
        unique (node)
    )""")
    conn.commit()
    conn.close()

# Create new data file
if not os.path.isfile(CSV_FILE):
    with open('data.csv', 'a', newline='') as file:
        writer = csv.writer(file)
        field = ["time", "node", "value"]
        writer.writerow(field)

def write_devices_file(node):
    db_conn = sqlite3.connect(DEVICES_FILE)
    db_cursor = db_conn.cursor()
    db_cursor.execute(
        "INSERT OR IGNORE INTO devices_list VALUES(:id, :node)",
        {'id': None, 'node': str(node)}
    )
    db_conn.commit()
    db_cursor.close()
    db_conn.close()

def write_data_file(node, date_time, value):
    # Convert date_time to Unix timestamp
    timestamp = int(dateutil.parser.parse(date_time).timestamp())

    db_conn = sqlite3.connect(DATA_FILE)
    db_cursor = db_conn.cursor()
    db_cursor.execute(
        "INSERT INTO sensor_data VALUES(:id, :node, :date_time, :value)",
        {'id': None, 'node': str(node), 'date_time': timestamp, 'value': str(value)}
    )
    db_conn.commit()
    db_cursor.close()
    db_conn.close()

def serial_thread():
    global running
    buffer = b''  # Buffer to hold incoming data

    while running is True:
        # Read incoming data
        new_data = port.read(25)  # Adjust the read size as needed

        if not new_data:
            continue

        buffer += new_data

        while buffer:
            # Find the index of the next start delimiter
            start_idx = buffer.find(b'\x7E')

            if start_idx == -1:
                buffer = b''  # Discard incomplete packets
                break

            # If the start delimiter is not at the beginning, discard bytes before it
            if start_idx > 0:
                buffer = buffer[start_idx:]

            # Check if there's enough data for a complete packet
            if len(buffer) < 20:  # Adjust based on packet structure
                break

            # Extract and process the complete packet
            complete_packet = buffer[:20]  # Adjust based on packet structure
            buffer = buffer[20:]  # Remove the processed packet from the buffer

            # Process the packet as before
            hex_representation = complete_packet.hex()

            hex_representation = hex_representation.upper()

            # Interpret the API frame structure
            start_delimiter = hex_representation[0:2]
            length = hex_representation[2:6]
            frame_type = hex_representation[6:8]
            source_address_64 = hex_representation[8:24]
            source_address_16 = hex_representation[24:28]
            receive_options = hex_representation[28:30]
            data_hex = hex_representation[30:38]
            checksum_hex = hex_representation[38:40]

            # Convert data to ASCII
            data_ascii = bytes.fromhex(data_hex).decode('utf-8', errors='replace')

            # Print the interpreted values
            # print(f"Raw Hex: {hex_representation}")
            # print(f"Start Delimiter: {start_delimiter}")
            # print(f"Length: {length}")
            # print(f"Frame Type: {frame_type}")
            # print(f"64-bit Source Address: {source_address_64}")
            # print(f"16-bit Source Address: {source_address_16}")
            # print(f"Receive Options: {receive_options}")
            # print(f"Data (Hex): {data_hex}")
            # print(f"Data (ASCII): {data_ascii}")
            # print(f"Checksum: {checksum_hex}")

            t = datetime.datetime.now(tz=pytz.utc)
            date_time_str = t.isoformat()
            write_data_file(
                source_address_64,
                date_time_str,
                data_ascii
            )

            write_devices_file(source_address_64)

            global current_value
            current_value = data_ascii

            print(source_address_64 + " " + data_ascii)

# Flask routes
@app.route('/')
@app.route('/<device>/<action>')
def index(device=None, action=None):
    global running

    thread = threading.Thread(target=serial_thread)

    if device:
        if action == 'on':
            if not running:
                print('Starting')
                running = True
                thread.start()
            else:
                print('Already running')
        elif action == 'off':
            if running:
                print('Stopping')
                running = False
            else:
                print('Not running')

    return render_template("index.html")

@app.route('/devices', methods=['GET'])
def get_devices():
    conn = sqlite3.connect(DEVICES_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT id, node FROM devices_list')
    device_rows = cursor.fetchall()

    devices = [{'id': row[0], 'node': row[1]} for row in device_rows]

    conn.close()

    return jsonify(devices)


@app.route('/data', methods=["GET", "POST"])
def data():
    range_param = request.args.get('range')
    device_param = request.args.get('device')

    print('Received Request - Range:', range_param, 'Device:', device_param)  # Add this line for debugging

    if device_param:
        conn = sqlite3.connect(DATA_FILE)
        cursor = conn.cursor()

        if range_param:
            range_seconds = 0
            if range_param == '1h':
                range_seconds = 3600
            elif range_param == '24h':
                range_seconds = 24 * 3600
            elif range_param == '1w':
                range_seconds = 7 * 24 * 3600
            elif range_param == '1m':
                range_seconds = 30 * 24 * 3600

            # Get the current time in seconds since epoch
            current_time = int(time.time())

            # Calculate the start time based on the range
            start_time = current_time - range_seconds

            cursor.execute(
                "SELECT date_time, value FROM sensor_data WHERE node = ? AND date_time >= ? ORDER BY date_time ASC",
                (device_param, start_time)
            )
        else:
            cursor.execute(
                "SELECT date_time, value FROM sensor_data WHERE node = ? ORDER BY date_time ASC",
                (device_param,)
            )

        data = cursor.fetchall()
        cursor.close()
        conn.close()

        # Format the data as a list of dictionaries
        filtered_data = [
            {"date_time": str(int(row[0]) * 1000), "value": row[1]} for row in data
        ]

        return jsonify(filtered_data)

    # If no specific device is provided, return an empty list
    return jsonify([])

if __name__ == "__main__":
    app.run()
