# Zigbee USB Serial Data Logger with Flask Web Interface

This repository contains a Python application that captures data from a serial port and stores it in an SQLite database. The application is accompanied by a Flask web interface that allows you to manage data capture and explore captured data conveniently.

## Prerequisites

Before you start, ensure you have the following prerequisites installed:

- Python 3.x
- Flask
- python-dateutil
- pytz
- pyftdi

## Installing pyftdi

For setting up `pyftdi`, please follow the installation instructions based on your operating system by visiting the official documentation:

[pyftdi Installation Instructions](https://eblot.github.io/pyftdi/installation.html)

## Getting Started

1. **Clone the Repository**

   Clone this repository to your local machine or download the ZIP archive and extract it.


2. **Install Dependencies**

   Open a terminal and navigate to the project directory. Run the following command to install the required dependencies:

   ```bash
   pip install -r requirements.txt

1. **Run the Application**

   Launch the application by running the app.py script:

   ```bash
   python app.py

2. **Access the Web Interface**
   Open a web browser and go to `http://localhost:5000`. This wil llead you to the main page of the web interface

## Web Interface Features

### Control Data Capture

- Start capturing data for a specific device by visiting `http://localhost:5000/device_name/on`.
- Stop capturing data for a specific device by visiting `http://localhost:5000/device_name/off`.

### View Captured Data

Retrieve captured data in JSON format by visiting:
`http://localhost:5000/data?device=device_name&range=1h`
Customize the time range (`1h`, `24h`, `1w`, `1m`) to suit your requirements.

### List Captured Devices

Fetch a list of devices that have been captured by visiting:
`http://localhost:5000/devices`

## File Descriptions

- `app.py`: The core application script that manages data capture, serial communication, and database operations.
- `index.html`: HTML template for the web interface.

## Customization

- Adapt the serial port URL (`'ftdi://ftdi:232:/1'`) in the `app.py` script to match your hardware configuration.
- Modify the packet structure and parsing logic within the `serial_thread` function as per your data format.
