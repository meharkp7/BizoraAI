"""IoT systems pack: controllers, sensors, radios, actuators, power, cloud.

Catalog entries and detection profile moved verbatim from the former
core registry into pack data, wired to the generic pack harness.
"""

from typing import Any

from bizora.core.entity_registry import EntityTypeDef, InterfaceDef
from bizora.packs.lexical import LexicalPack, data_iface, power_iface

POWER = {"name": "power", "kind": "power", "params": {}}
DATA = {"name": "data", "kind": "data", "params": {}}
GPIO = {"name": "gpio", "kind": "gpio", "params": {}}

COMPONENTS: list[dict[str, Any]] = [
    {
        "component_id": "mcu-esp32-wroom32",
        "domain": "iot",
        "entity_type": "microcontroller",
        "category": "compute",
        "kind": "component",
        "label": "ESP32-WROOM-32 module",
        "generic": False,
        "manufacturer": "Espressif Systems",
        "part_number": "ESP32-WROOM-32",
        "headline": "Wi-Fi + Bluetooth MCU module, 240 MHz dual-core, 3.3 V",
        "description": (
            "ESP32-WROOM-32 wireless module with an ESP32-D0WDQ6 dual-core MCU, "
            "integrated Wi-Fi and Bluetooth, and 3.3 V logic throughout."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "CPU", "value": "Xtensa dual-core 240 MHz", "typical": False},
            {"name": "Wireless", "value": "Wi-Fi 4 + Bluetooth 4.2", "typical": False},
            {"name": "Logic level", "value": "3.3", "unit": "V", "typical": False},
            {"name": "Flash", "value": "4", "unit": "MB", "typical": True},
            {"name": "GPIO", "value": "34", "typical": False},
        ],
        "pinout": [
            {"designator": "3V3", "name": "3V3", "function": "3.3 V supply output"},
            {"designator": "GND", "name": "GND", "function": "Ground"},
            {"designator": "EN", "name": "EN", "function": "Chip enable (pull high)"},
            {"designator": "TX0", "name": "GPIO1/TX0", "function": "UART0 transmit"},
            {"designator": "RX0", "name": "GPIO3/RX0", "function": "UART0 receive"},
            {"designator": "G21", "name": "GPIO21", "function": "Default I2C SDA"},
            {"designator": "G22", "name": "GPIO22", "function": "Default I2C SCL"},
        ],
        "interfaces": [
            POWER,
            GPIO,
            DATA,
            {"name": "i2c", "kind": "protocol", "params": {"voltage": "3.3V"}},
            {"name": "wifi", "kind": "rf", "params": {}},
        ],
        "constraints": {"supply_min_V": "3.0", "supply_max_V": "3.6", "io_max_V": "3.6"},
        "config_schema": [
            {
                "key": "model",
                "label": "Model",
                "type": "string",
                "default": "ESP32-WROOM-32",
                "required": True,
                "description": "Exact module part number.",
            },
            {
                "key": "i2c_sda_gpio",
                "label": "I2C SDA pin",
                "type": "number",
                "default": 21,
                "required": False,
                "description": "GPIO used for the I2C data line.",
            },
            {
                "key": "i2c_scl_gpio",
                "label": "I2C SCL pin",
                "type": "number",
                "default": 22,
                "required": False,
                "description": "GPIO used for the I2C clock line.",
            },
            {
                "key": "wifi_ssid",
                "label": "Wi-Fi SSID",
                "type": "string",
                "default": "",
                "required": False,
                "description": "Network name; empty means unprovisioned.",
            },
        ],
        "default_config": {"model": "ESP32-WROOM-32", "i2c_sda_gpio": 21, "i2c_scl_gpio": 22},
        "evidence": [
            {
                "source": "Espressif ESP32-WROOM-32 datasheet",
                "note": "Reference URL not verified from this environment.",
            },
        ],
    },
    {
        "component_id": "mcu-esp32-devkitc",
        "domain": "iot",
        "entity_type": "microcontroller",
        "category": "compute",
        "kind": "component",
        "label": "ESP32-DevKitC development board",
        "generic": False,
        "manufacturer": "Espressif Systems",
        "part_number": "ESP32-DevKitC",
        "headline": "ESP32 development board with USB-UART bridge, 5 V USB powered",
        "description": (
            "ESP32-DevKitC breaks out an ESP32-WROOM module with a USB-UART bridge "
            "and 3.3 V regulation for prototyping."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Module", "value": "ESP32-WROOM", "typical": False},
            {"name": "USB power", "value": "5", "unit": "V", "typical": False},
            {"name": "Logic level", "value": "3.3", "unit": "V", "typical": False},
        ],
        "pinout": [
            {"designator": "5V", "name": "5V", "function": "USB 5 V input"},
            {"designator": "3V3", "name": "3V3", "function": "Regulated 3.3 V output"},
            {"designator": "GND", "name": "GND", "function": "Ground"},
            {"designator": "TX", "name": "TX", "function": "UART transmit"},
            {"designator": "RX", "name": "RX", "function": "UART receive"},
        ],
        "interfaces": [POWER, GPIO, DATA],
        "constraints": {"supply_min_V": "4.5", "supply_max_V": "5.5", "io_max_V": "3.6"},
        "config_schema": [
            {
                "key": "model",
                "label": "Model",
                "type": "string",
                "default": "ESP32-DevKitC",
                "required": True,
                "description": "Exact board model.",
            },
        ],
        "default_config": {"model": "ESP32-DevKitC"},
        "evidence": [],
    },
    {
        "component_id": "mcu-arduino-uno",
        "domain": "iot",
        "entity_type": "microcontroller",
        "category": "compute",
        "kind": "component",
        "label": "Arduino Uno R3",
        "generic": False,
        "manufacturer": "Arduino",
        "part_number": "Uno R3",
        "headline": "ATmega328P board, 5 V logic, 14 digital + 6 analog pins",
        "description": (
            "Arduino Uno R3 with an ATmega328P at 16 MHz. Note 5 V logic: level "
            "shifting is required for 3.3 V I2C sensors."
        ),
        "datasheet_url": None,
        "reference_url": "https://docs.arduino.cc/hardware/uno-rev3/",
        "specs": [
            {"name": "MCU", "value": "ATmega328P 16 MHz", "typical": False},
            {"name": "Logic level", "value": "5", "unit": "V", "typical": False},
            {"name": "Digital I/O", "value": "14", "typical": False},
            {"name": "Analog inputs", "value": "6", "typical": False},
            {"name": "Flash", "value": "32", "unit": "KB", "typical": False},
        ],
        "pinout": [
            {"designator": "5V", "name": "5V", "function": "5 V rail"},
            {"designator": "3V3", "name": "3V3", "function": "3.3 V rail (150 mA max)"},
            {"designator": "GND", "name": "GND", "function": "Ground"},
            {"designator": "A4", "name": "A4/SDA", "function": "I2C data (5 V)"},
            {"designator": "A5", "name": "A5/SCL", "function": "I2C clock (5 V)"},
        ],
        "interfaces": [POWER, GPIO, DATA],
        "constraints": {"supply_min_V": "6", "supply_max_V": "20", "io_max_V": "5.5"},
        "config_schema": [
            {
                "key": "model",
                "label": "Model",
                "type": "string",
                "default": "Uno R3",
                "required": True,
                "description": "Exact board model.",
            },
        ],
        "default_config": {"model": "Uno R3"},
        "evidence": [
            {
                "source": "Arduino Uno Rev3 documentation",
                "note": "Verified reference URL.",
            },
        ],
    },
    {
        "component_id": "sensor-bme280",
        "domain": "iot",
        "entity_type": "sensor-module",
        "category": "sensor",
        "kind": "component",
        "label": "BME280 environmental sensor",
        "generic": False,
        "manufacturer": "Bosch Sensortec",
        "part_number": "BME280",
        "headline": "Temperature / humidity / pressure, I2C + SPI, 3.3 V",
        "description": (
            "BME280 integrated environmental sensor reporting temperature, humidity, "
            "and barometric pressure over I2C or SPI at 3.3 V logic."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Temperature range", "value": "-40 to +85", "unit": "°C", "typical": False},
            {"name": "Humidity range", "value": "0-100", "unit": "%RH", "typical": False},
            {"name": "Pressure range", "value": "300-1100", "unit": "hPa", "typical": False},
            {"name": "Interface", "value": "I2C / SPI", "typical": False},
            {"name": "Supply", "value": "1.7-3.6", "unit": "V", "typical": False},
        ],
        "pinout": [
            {"designator": "VCC", "name": "VCC", "function": "3.3 V supply"},
            {"designator": "GND", "name": "GND", "function": "Ground"},
            {"designator": "SCL", "name": "SCL", "function": "I2C clock"},
            {"designator": "SDA", "name": "SDA", "function": "I2C data"},
        ],
        "interfaces": [
            POWER,
            DATA,
            {"name": "i2c", "kind": "protocol", "params": {"voltage": "3.3V"}},
        ],
        "constraints": {"supply_min_V": "1.7", "supply_max_V": "3.6"},
        "config_schema": [
            {
                "key": "model",
                "label": "Model",
                "type": "string",
                "default": "BME280",
                "required": True,
                "description": "Exact sensor part number.",
            },
            {
                "key": "i2c_address",
                "label": "I2C address",
                "type": "enum",
                "default": "0x76",
                "options": ["0x76", "0x77"],
                "required": True,
                "description": "Seven-bit address set by the SDO pin.",
            },
            {
                "key": "sample_period_s",
                "label": "Sample period",
                "type": "number",
                "default": 60,
                "unit": "s",
                "required": False,
                "description": "Seconds between reported readings.",
            },
        ],
        "default_config": {"model": "BME280", "i2c_address": "0x76"},
        "evidence": [
            {
                "source": "Bosch Sensortec BME280 datasheet",
                "note": "Reference URL not verified from this environment.",
            },
        ],
    },
    {
        "component_id": "sensor-dht22",
        "domain": "iot",
        "entity_type": "sensor-module",
        "category": "sensor",
        "kind": "component",
        "label": "DHT22 temperature and humidity sensor",
        "generic": False,
        "manufacturer": "Aosong",
        "part_number": "DHT22",
        "headline": "Temperature / humidity, single-wire, 3.3-5 V",
        "description": (
            "DHT22 (AM2302) digital temperature and humidity sensor over a "
            "single-wire protocol. Slower and less accurate than the BME280."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Temperature range", "value": "-40 to +80", "unit": "°C", "typical": False},
            {"name": "Humidity range", "value": "0-100", "unit": "%RH", "typical": False},
            {"name": "Interface", "value": "single-wire", "typical": False},
            {"name": "Supply", "value": "3.3-5", "unit": "V", "typical": False},
        ],
        "pinout": [
            {"designator": "VCC", "name": "VCC", "function": "Supply"},
            {"designator": "DATA", "name": "DATA", "function": "Single-wire data"},
            {"designator": "GND", "name": "GND", "function": "Ground"},
        ],
        "interfaces": [POWER, DATA],
        "constraints": {"supply_min_V": "3.3", "supply_max_V": "5.5"},
        "config_schema": [
            {
                "key": "model",
                "label": "Model",
                "type": "string",
                "default": "DHT22",
                "required": True,
                "description": "Exact sensor part number.",
            },
            {
                "key": "data_gpio",
                "label": "Data pin",
                "type": "number",
                "default": 4,
                "required": True,
                "description": "Controller GPIO wired to the DATA pin.",
            },
        ],
        "default_config": {"model": "DHT22"},
        "evidence": [{"source": "Aosong DHT22 datasheet", "note": "Electrical ratings."}],
    },
    {
        "component_id": "sensor-hcsr04",
        "domain": "iot",
        "entity_type": "sensor-module",
        "category": "sensor",
        "kind": "component",
        "label": "HC-SR04 ultrasonic distance sensor",
        "generic": False,
        "manufacturer": "multi-source",
        "part_number": "HC-SR04",
        "headline": "Ultrasonic ranging 2-400 cm, trigger/echo, 5 V",
        "description": (
            "HC-SR04 ultrasonic distance module with trigger/echo pins. The echo "
            "output is 5 V and needs a divider for 3.3 V controllers."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Range", "value": "2-400", "unit": "cm", "typical": False},
            {"name": "Supply", "value": "5", "unit": "V", "typical": False},
            {"name": "Echo level", "value": "5", "unit": "V", "typical": False},
        ],
        "pinout": [
            {"designator": "VCC", "name": "VCC", "function": "5 V supply"},
            {"designator": "TRIG", "name": "TRIG", "function": "Trigger input"},
            {"designator": "ECHO", "name": "ECHO", "function": "Echo output (5 V)"},
            {"designator": "GND", "name": "GND", "function": "Ground"},
        ],
        "interfaces": [POWER, DATA],
        "constraints": {"supply_min_V": "4.5", "supply_max_V": "5.5"},
        "config_schema": [
            {
                "key": "model",
                "label": "Model",
                "type": "string",
                "default": "HC-SR04",
                "required": True,
                "description": "Exact module model.",
            },
            {
                "key": "trig_gpio",
                "label": "Trigger pin",
                "type": "number",
                "default": 5,
                "required": True,
                "description": "Controller GPIO wired to TRIG.",
            },
            {
                "key": "echo_gpio",
                "label": "Echo pin",
                "type": "number",
                "default": 18,
                "required": True,
                "description": "Controller GPIO wired to ECHO (via divider).",
            },
        ],
        "default_config": {"model": "HC-SR04"},
        "evidence": [],
    },
    {
        "component_id": "temp-sensor-generic",
        "domain": "iot",
        "entity_type": "sensor-module",
        "category": "sensor",
        "kind": "component",
        "label": "Temperature sensor (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Correctly identified generic temperature sensor",
        "description": (
            "Generic temperature-sensing element where the system names no exact "
            "sensor. Replace with a BME280-class part for real readings."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [POWER, DATA],
        "constraints": {},
        "config_schema": [
            {
                "key": "sample_period_s",
                "label": "Sample period",
                "type": "number",
                "default": 60,
                "unit": "s",
                "required": False,
                "description": "Seconds between reported readings.",
            },
        ],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "radio-sx1276",
        "domain": "iot",
        "entity_type": "radio",
        "category": "network",
        "kind": "component",
        "label": "SX1276 LoRa transceiver",
        "generic": False,
        "manufacturer": "Semtech",
        "part_number": "SX1276",
        "headline": "Sub-GHz LoRa transceiver, SPI host, 3.3 V",
        "description": (
            "SX1276 long-range spread-spectrum transceiver for LoRa links, "
            "hosted over SPI from the controller."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Bands", "value": "137-1020 MHz", "typical": False},
            {"name": "Host interface", "value": "SPI", "typical": False},
            {"name": "Supply", "value": "1.8-3.7", "unit": "V", "typical": False},
        ],
        "pinout": [
            {"designator": "VCC", "name": "VCC", "function": "3.3 V supply"},
            {"designator": "GND", "name": "GND", "function": "Ground"},
            {"designator": "SCK", "name": "SCK", "function": "SPI clock"},
            {"designator": "MISO", "name": "MISO", "function": "SPI data out"},
            {"designator": "MOSI", "name": "MOSI", "function": "SPI data in"},
            {"designator": "NSS", "name": "NSS", "function": "SPI chip select"},
        ],
        "interfaces": [
            POWER,
            {"name": "air", "kind": "rf", "params": {}},
            DATA,
        ],
        "constraints": {"supply_min_V": "1.8", "supply_max_V": "3.7"},
        "config_schema": [
            {
                "key": "model",
                "label": "Model",
                "type": "string",
                "default": "SX1276",
                "required": True,
                "description": "Exact transceiver part number.",
            },
            {
                "key": "frequency_mhz",
                "label": "Frequency",
                "type": "number",
                "default": 868,
                "unit": "MHz",
                "required": True,
                "description": "Carrier frequency for this deployment.",
            },
        ],
        "default_config": {"model": "SX1276"},
        "evidence": [{"source": "Semtech SX1276 datasheet", "note": "Electrical ratings."}],
    },
    {
        "component_id": "actuator-relay-generic",
        "domain": "iot",
        "entity_type": "actuator",
        "category": "compute",
        "kind": "component",
        "label": "Relay module (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic optically isolated relay output",
        "description": (
            "Generic relay output for switching mains-class loads from a logic "
            "signal. No exact module is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [
            {"designator": "VCC", "name": "VCC", "function": "Coil supply"},
            {"designator": "GND", "name": "GND", "function": "Ground"},
            {"designator": "IN", "name": "IN", "function": "Logic control input"},
        ],
        "interfaces": [POWER, {"name": "control", "kind": "signal", "params": {}}],
        "constraints": {},
        "config_schema": [
            {
                "key": "control_gpio",
                "label": "Control pin",
                "type": "number",
                "default": 26,
                "required": True,
                "description": "Controller GPIO driving the relay input.",
            },
        ],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "actuator-sg90",
        "domain": "iot",
        "entity_type": "actuator",
        "category": "compute",
        "kind": "component",
        "label": "SG90 servo motor",
        "generic": False,
        "manufacturer": "Tower Pro",
        "part_number": "SG90",
        "headline": "Micro servo, 180-degree, PWM control, 5 V",
        "description": (
            "SG90 micro servo for positioning duty, driven by a 50 Hz PWM control "
            "signal at 5 V supply."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Travel", "value": "180", "unit": "deg", "typical": False},
            {"name": "Supply", "value": "4.8-5", "unit": "V", "typical": False},
            {"name": "Control", "value": "50 Hz PWM", "typical": False},
        ],
        "pinout": [
            {"designator": "VCC", "name": "VCC", "function": "5 V supply"},
            {"designator": "GND", "name": "GND", "function": "Ground"},
            {"designator": "SIG", "name": "SIG", "function": "PWM control input"},
        ],
        "interfaces": [POWER, {"name": "control", "kind": "signal", "params": {}}],
        "constraints": {"supply_min_V": "4.5", "supply_max_V": "5.5"},
        "config_schema": [
            {
                "key": "model",
                "label": "Model",
                "type": "string",
                "default": "SG90",
                "required": True,
                "description": "Exact servo model.",
            },
            {
                "key": "control_gpio",
                "label": "Control pin",
                "type": "number",
                "default": 13,
                "required": True,
                "description": "Controller GPIO producing the PWM signal.",
            },
        ],
        "default_config": {"model": "SG90"},
        "evidence": [],
    },
    {
        "component_id": "psu-3v3-generic",
        "domain": "iot",
        "entity_type": "power-supply",
        "category": "power",
        "kind": "component",
        "label": "3.3 V supply (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic regulated 3.3 V node supply",
        "description": (
            "Generic 3.3 V supply for sensor nodes. Replace with an exact regulator "
            "or battery pack for deployment design."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [{"designator": "3V3", "name": "3V3", "function": "Regulated output"}],
        "interfaces": [POWER],
        "constraints": {},
        "config_schema": [
            {
                "key": "supply_V",
                "label": "Output voltage",
                "type": "number",
                "default": 3.3,
                "unit": "V",
                "required": True,
                "description": "Regulated output voltage.",
            },
        ],
        "default_config": {"supply_V": 3.3},
        "evidence": [],
    },
    {
        "component_id": "cloud-mqtt-generic",
        "domain": "iot",
        "entity_type": "cloud-service",
        "category": "network",
        "kind": "output",
        "label": "MQTT broker (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic MQTT telemetry broker endpoint",
        "description": (
            "Generic MQTT broker receiving node telemetry. Set the topic namespace "
            "and broker host for the deployment."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [{"name": "api", "kind": "protocol", "params": {}}],
        "constraints": {},
        "config_schema": [
            {
                "key": "broker_host",
                "label": "Broker host",
                "type": "string",
                "default": "",
                "required": False,
                "description": "Broker hostname; empty means unprovisioned.",
            },
            {
                "key": "topic_prefix",
                "label": "Topic prefix",
                "type": "string",
                "default": "bizora/telemetry",
                "required": True,
                "description": "MQTT topic namespace for this deployment.",
            },
        ],
        "default_config": {"topic_prefix": "bizora/telemetry"},
        "evidence": [],
    },
    {
        "component_id": "cloud-dashboard-generic",
        "domain": "iot",
        "entity_type": "cloud-service",
        "category": "network",
        "kind": "output",
        "label": "Cloud dashboard (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic telemetry dashboard sink",
        "description": (
            "Generic cloud dashboard consuming telemetry from the broker. "
            "No exact product is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [{"name": "api", "kind": "protocol", "params": {}}],
        "constraints": {},
        "config_schema": [],
        "default_config": {},
        "evidence": [],
    },
]


PACK_ID = "iot"
PACK_VERSION = "1.0.0"
DISPLAY = "IoT systems"
THRESHOLD = 2

SIGNALS: tuple[str, ...] = (
    "sensor",
    "microcontroller",
    "esp32",
    "arduino",
    "actuator",
    "wireless",
    "bluetooth",
    "wifi",
    "lora",
    "zigbee",
    "mqtt",
    "gpio",
    "i2c",
    "spi",
    "uart",
    "embedded",
    "firmware",
    "gateway",
    "dashboard",
)

ENTITY_TYPES: tuple[EntityTypeDef, ...] = (
    EntityTypeDef(
        "microcontroller",
        "Microcontroller",
        "compute",
        ("microcontroller", "mcu", "esp32", "arduino", "raspberry", "stm32"),
        (power_iface(), InterfaceDef("gpio", "gpio"), data_iface()),
        identity_keys=("model", "part"),
    ),
    EntityTypeDef(
        "sensor-module",
        "Sensor module",
        "sensor",
        ("sensor", "temperature", "humidity", "pressure", "accelerometer", "dht", "bme"),
        (power_iface(), data_iface()),
        identity_keys=("model", "part"),
    ),
    EntityTypeDef(
        "actuator",
        "Actuator",
        "compute",
        ("actuator", "relay", "motor", "servo", "valve"),
        (power_iface(), InterfaceDef("control", "signal")),
    ),
    EntityTypeDef(
        "radio",
        "Radio / comms",
        "network",
        (
            "radio",
            "wireless",
            "wifi",
            "bluetooth",
            "lora",
            "zigbee",
            "transceiver",
            "antenna",
        ),
        (power_iface(), InterfaceDef("air", "rf"), data_iface()),
    ),
    EntityTypeDef(
        "cloud-service",
        "Cloud service",
        "network",
        ("cloud", "dashboard", "server", "mqtt broker", "backend", "api"),
        (InterfaceDef("api", "protocol"),),
    ),
    EntityTypeDef(
        "power-supply",
        "Power supply",
        "power",
        ("battery", "power supply", "solar", "charger", "regulator"),
        (power_iface(),),
    ),
)

pack = LexicalPack(
    pack_id=PACK_ID,
    pack_version=PACK_VERSION,
    display=DISPLAY,
    signals=SIGNALS,
    threshold=THRESHOLD,
    entity_types=ENTITY_TYPES,
    catalog=COMPONENTS,
    simulator_adapter_ids=(),
)
