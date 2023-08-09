import pyftdi.serialext
from flask import Flask, render_template, make_response, jsonify, request
import datetime
import time
import csv
import sqlite3
import configparser
import os
import pytz
import threading
import dateutil.parser
from pathlib import Path

from getpass import getpass
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)

# Paths and configuration
source_path = Path(__file__).resolve()
source_dir = source_path.parent
config = configparser.ConfigParser()
configLocation = str(source_dir) + "/configfile.ini"

# Open a serial port on the second FTDI device interface (IF/2) @ 115200 baud
port = pyftdi.serialext.serial_for_url('ftdi://ftdi:232:/1', baudrate=115200)

current_value = "0"

# Client setup
running = False


def write_file():
    with open(configLocation, "w") as configfile:
        config.write(configfile)

# Configuration setup
config = configparser.ConfigParser()
if not os.path.exists(configLocation):
    config["MySQLConfig"] = {
        "host": "localhost",
        "user": "username",
        "password": "password",
        "port": "3306",
    }
    write_file()
else:
    config.read(configLocation)
    print(config.sections())

sqlhost = config.get("MySQLConfig", "host")
sqluser = config.get("MySQLConfig", "user")
sqlpass = config.get("MySQLConfig", "password")
sqlport = config.get("MySQLConfig", "port")

try:
    with mysql.connector.connect(
        host=sqlhost,
        user=sqluser,
        password=sqlpass,
        port=sqlport,
    ) as connection:
        create_db_query = "CREATE DATABASE IF NOT EXISTS zigbee_data"
        with connection.cursor() as cursor:
            cursor.execute(create_db_query)
        
        # Select the database
        connection.database = "zigbee_data"
        
        # Create 'sensor_data' table if it doesn't exist
        create_sensor_data_table_query = """
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            node VARCHAR(255),
            date_time DATETIME,
            value TEXT
        )
        """
        with connection.cursor() as cursor:
            cursor.execute(create_sensor_data_table_query)
        
        # Create 'devices_list' table if it doesn't exist
        create_devices_list_table_query = """
        CREATE TABLE IF NOT EXISTS devices_list (
            id INT AUTO_INCREMENT PRIMARY KEY,
            node VARCHAR(255) UNIQUE
        )
        """
        with connection.cursor() as cursor:
            cursor.execute(create_devices_list_table_query)
except Error as e:
    print(e)

def write_devices_file(node):
    try:
        with mysql.connector.connect(
            host=sqlhost,
            user=sqluser,
            password=sqlpass,
            database="zigbee_data",
            port=sqlport,
        ) as connection:
            insert_query = "INSERT IGNORE INTO devices_list (node) VALUES (%s)"
            with connection.cursor() as cursor:
                cursor.execute(insert_query, (str(node),))
                connection.commit()
    except Error as e:
        print(e)

def write_data_file(node, date_time, value):
    try:
        with mysql.connector.connect(
            host=sqlhost,
            user=sqluser,
            password=sqlpass,
            database="zigbee_data",
            port=sqlport,
        ) as connection:
            insert_query = "INSERT INTO sensor_data (node, date_time, value) VALUES (%s, %s, %s)"
            with connection.cursor() as cursor:
                cursor.execute(insert_query, (str(node), date_time, str(value)))
                connection.commit()
    except Error as e:
        print(e)


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

            t = datetime.datetime.now(tz=pytz.utc)
            date_time_str = t.isoformat()

            # Filter out non-ASCII characters from data_ascii
            data_ascii = ''.join(char for char in data_ascii if char.isascii())

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
    try:
        with mysql.connector.connect(
            host=sqlhost,
            user=sqluser,
            password=sqlpass,
            database="zigbee_data",
            port=sqlport,
        ) as connection:
            select_query = "SELECT id, node FROM devices_list"
            with connection.cursor() as cursor:
                cursor.execute(select_query)
                device_rows = cursor.fetchall()

                devices = [{'id': row[0], 'node': row[1]} for row in device_rows]

                return jsonify(devices)
    except Error as e:
        print(e)
        return jsonify([])


@app.route('/data', methods=["GET", "POST"])
def data():
    range_param = request.args.get('range')
    device_param = request.args.get('device')

    print('Received Request - Range:', range_param, 'Device:', device_param)  # Add this line for debugging

    if device_param:
        try:
            with mysql.connector.connect(
                host=sqlhost,
                user=sqluser,
                password=sqlpass,
                database="zigbee_data",
                port=sqlport,
            ) as connection:
                cursor = connection.cursor()

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

                    select_query = "SELECT date_time, value FROM sensor_data WHERE node = %s AND date_time >= %s ORDER BY date_time ASC"
                    cursor.execute(select_query, (device_param, start_time))
                else:
                    select_query = "SELECT date_time, value FROM sensor_data WHERE node = %s ORDER BY date_time ASC"
                    cursor.execute(select_query, (device_param,))

                data = cursor.fetchall()
                cursor.close()

                # Format the data as a list of dictionaries with properly formatted timestamps
                filtered_data = [
                    {"date_time": row[0].timestamp() * 1000, "value": row[1]} for row in data
                ]

                return jsonify(filtered_data)
        except Error as e:
            print(e)
            return jsonify([])

    # If no specific device is provided, return an empty list
    return jsonify([])

if __name__ == "__main__":
    app.run()
