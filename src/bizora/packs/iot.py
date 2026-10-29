"""IoT systems pack: controllers, sensors, radios, actuators, power, cloud.

Phase 9 upgrades the v1 lexical placeholder with link preflight: swaps
are validated against the candidate's own config schema (required keys,
types, enum options) and assigned GPIO pins must be distinct. Detection,
resolution, rendering, and copilot tools still delegate to the generic
lexical harness over unchanged v1 data.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from bizora.contracts.assets import ProceduralSpec
from bizora.contracts.graph import GraphNode, MethodologyGraph
from bizora.contracts.packs import (
    CopilotToolSpec,
    DomainTag,
    PackPreflightFinding,
    PackPreflightSeverity,
    PackVocabulary,
    PartRef,
    PartResolution,
    RenderSpec,
    SimulationPreview,
    TelemetryMapping,
)
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.core.entity_registry import EntityTypeDef, InterfaceDef
from bizora.packs.lexical import LexicalPack, data_iface, power_iface

if TYPE_CHECKING:
    from bizora.contracts.components import ComponentDetail, ConfigField
    from bizora.core.entity_registry import DomainProfile

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


# ---------------------------------------------------------------------------
# Part visuals: per-part assemblies from datasheet dimensions.
# ---------------------------------------------------------------------------
#
# Each row models one catalog part as placed solids in millimetres.
# Dimensions come from the cited source; anything the source does not
# state (sub-placement, omitted pins, representative outlines) is
# called out in the row note. Rows validate at import so a bad
# dimension breaks loudly instead of rendering a wrong part.

PART_VISUALS: dict[str, dict[str, Any]] = {
    "mcu-esp32-wroom32": {
        "outline": "ESP32-WROOM-32",
        "source": "Espressif ESP32-WROOM-32 datasheet v2.9 "
        "(18.00 x 25.50 x 3.10 mm, 38 pins, 1.27 mm pitch)",
        "note": "Castellated edge pads approximated by edge pins; "
        "shield-can extent within the datasheet outline; antenna keep-out left bare.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 25.5,
                "body_width_mm": 18.0,
                "body_height_mm": 0.8,
                "pin_count": 38,
                "pin_pitch_mm": 1.27,
                "pin_rows": 2,
                "pin_length_mm": 1.0,
                "body_name": "pcb",
            },
            {
                "kind": "box",
                "body_length_mm": 18.0,
                "body_width_mm": 17.0,
                "body_height_mm": 2.2,
                "pin_count": 0,
                "offset_mm": (-3.25, 0.8, 0.0),
                "body_name": "can",
            },
        ],
    },
    "mcu-esp32-devkitc": {
        "outline": "ESP32-DevKitC V4",
        "source": "Espressif DevKitC V4 (54.4 x 27.9 mm board, 2x19 headers)",
        "note": "Female-header below-board stubs, buttons, and passives omitted; "
        "module pins hidden by soldering.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 54.4,
                "body_width_mm": 27.9,
                "body_height_mm": 1.6,
                "pin_count": 0,
                "body_name": "pcb",
            },
            {
                "kind": "box",
                "body_length_mm": 25.5,
                "body_width_mm": 18.0,
                "body_height_mm": 0.8,
                "pin_count": 0,
                "offset_mm": (-13.45, 1.6, 0.0),
                "body_name": "pcb",
            },
            {
                "kind": "box",
                "body_length_mm": 18.0,
                "body_width_mm": 17.0,
                "body_height_mm": 2.2,
                "pin_count": 0,
                "offset_mm": (-16.7, 2.4, 0.0),
                "body_name": "can",
            },
            {
                "kind": "box",
                "body_length_mm": 48.26,
                "body_width_mm": 2.54,
                "body_height_mm": 8.5,
                "pin_count": 0,
                "offset_mm": (0.0, 1.6, -10.68),
                "body_name": "header",
            },
            {
                "kind": "box",
                "body_length_mm": 48.26,
                "body_width_mm": 2.54,
                "body_height_mm": 8.5,
                "pin_count": 0,
                "offset_mm": (0.0, 1.6, 10.68),
                "body_name": "header",
            },
            {
                "kind": "box",
                "body_length_mm": 7.5,
                "body_width_mm": 5.7,
                "body_height_mm": 2.8,
                "pin_count": 0,
                "offset_mm": (23.45, 1.6, 0.0),
                "body_name": "usb",
            },
        ],
    },
    "mcu-arduino-uno": {
        "outline": "Arduino Uno R3",
        "source": "Arduino Uno R3 reference (68.6 x 53.4 mm PCB; headers "
        "6/8/8/10 at 2.54 mm; USB-B ~16 x 12.5 x 11 mm)",
        "note": "Header positions approximate within the outline; barrel jack "
        "and small passives omitted.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 68.6,
                "body_width_mm": 53.4,
                "body_height_mm": 1.6,
                "pin_count": 0,
                "body_name": "pcb",
            },
            {
                "kind": "box",
                "body_length_mm": 16.0,
                "body_width_mm": 12.5,
                "body_height_mm": 11.0,
                "pin_count": 0,
                "offset_mm": (-24.0, 1.6, -18.0),
                "body_name": "usb",
            },
            {
                "kind": "box",
                "body_length_mm": 34.8,
                "body_width_mm": 6.35,
                "body_height_mm": 4.0,
                "pin_count": 28,
                "pin_pitch_mm": 2.54,
                "pin_rows": 2,
                "pin_length_mm": 2.0,
                "offset_mm": (5.0, 1.6, 2.0),
                "body_name": "body",
            },
            {
                "kind": "box",
                "body_length_mm": 12.7,
                "body_width_mm": 2.54,
                "body_height_mm": 8.5,
                "pin_count": 0,
                "offset_mm": (-15.0, 1.6, -23.7),
                "body_name": "header",
            },
            {
                "kind": "box",
                "body_length_mm": 17.78,
                "body_width_mm": 2.54,
                "body_height_mm": 8.5,
                "pin_count": 0,
                "offset_mm": (12.0, 1.6, -23.7),
                "body_name": "header",
            },
            {
                "kind": "box",
                "body_length_mm": 17.78,
                "body_width_mm": 2.54,
                "body_height_mm": 8.5,
                "pin_count": 0,
                "offset_mm": (-12.0, 1.6, 23.7),
                "body_name": "header",
            },
            {
                "kind": "box",
                "body_length_mm": 22.86,
                "body_width_mm": 2.54,
                "body_height_mm": 8.5,
                "pin_count": 0,
                "offset_mm": (12.0, 1.6, 23.7),
                "body_name": "header",
            },
        ],
    },
    "sensor-hcsr04": {
        "outline": "HC-SR04",
        "source": "HC-SR04 dimensions (45 x 20 mm board, 16 mm transducers, "
        "4-pin header)",
        "note": "Transducer centers symmetric within the outline (clones vary); "
        "crystal omitted.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 45.0,
                "body_width_mm": 20.0,
                "body_height_mm": 1.6,
                "pin_count": 0,
                "body_name": "pcb",
            },
            {
                "kind": "cylinder",
                "body_length_mm": 16.0,
                "body_width_mm": 16.0,
                "body_height_mm": 12.0,
                "pin_count": 0,
                "offset_mm": (-13.0, 1.6, 0.0),
                "body_name": "can",
            },
            {
                "kind": "cylinder",
                "body_length_mm": 16.0,
                "body_width_mm": 16.0,
                "body_height_mm": 12.0,
                "pin_count": 0,
                "offset_mm": (13.0, 1.6, 0.0),
                "body_name": "can",
            },
            {
                "kind": "box",
                "body_length_mm": 2.54,
                "body_width_mm": 10.16,
                "body_height_mm": 2.5,
                "pin_count": 4,
                "pin_pitch_mm": 2.54,
                "pin_rows": 4,
                "pin_length_mm": 5.0,
                "offset_mm": (0.0, 1.6, 4.5),
                "body_name": "header",
            },
        ],
    },
    "sensor-dht22": {
        "outline": "DHT22 / AM2302",
        "source": "Adafruit DHT22 (15.1 x 25 x 7.7 mm body, 4 pins at 0.1 in)",
        "note": "Single-row leads; lead length typical.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 15.1,
                "body_width_mm": 25.0,
                "body_height_mm": 7.7,
                "pin_count": 4,
                "pin_pitch_mm": 2.54,
                "pin_rows": 4,
                "pin_length_mm": 6.0,
                "body_name": "body",
            },
        ],
    },
    "sensor-bme280": {
        "outline": "BME280 LGA-8",
        "source": "Bosch BME280 datasheet (2.5 x 2.5 x 0.93 mm metal-lid LGA-8)",
        "note": "LGA pads face the board and are not modeled; the lid marks "
        "the sensor cavity.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 2.5,
                "body_width_mm": 2.5,
                "body_height_mm": 0.78,
                "pin_count": 0,
                "body_name": "body",
            },
            {
                "kind": "box",
                "body_length_mm": 2.2,
                "body_width_mm": 2.2,
                "body_height_mm": 0.15,
                "pin_count": 0,
                "offset_mm": (0.0, 0.78, 0.0),
                "body_name": "lid",
            },
        ],
    },
    "radio-sx1276": {
        "outline": "SX1276 QFN-28",
        "source": "Semtech SX1276 (28-QFN 6 x 6 mm, 0.5 mm pitch)",
        "note": "Height nominal QFN profile.",
        "solids": [
            {
                "kind": "qfn",
                "body_length_mm": 6.0,
                "body_width_mm": 6.0,
                "body_height_mm": 0.8,
                "pin_count": 28,
                "pin_pitch_mm": 0.5,
                "pin_rows": 4,
                "pin_length_mm": 0.3,
                "body_name": "body",
            },
        ],
    },
    "actuator-sg90": {
        "outline": "SG90",
        "source": "Tower Pro SG90 (23.0 x 12.2 x 29.0 mm, 32.3 mm flange span)",
        "note": "Flange height and shaft approximate; wire omitted.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 23.0,
                "body_width_mm": 12.2,
                "body_height_mm": 29.0,
                "pin_count": 0,
                "body_name": "body",
            },
            {
                "kind": "box",
                "body_length_mm": 32.3,
                "body_width_mm": 12.2,
                "body_height_mm": 2.5,
                "pin_count": 0,
                "offset_mm": (0.0, 22.0, 0.0),
                "body_name": "flange",
            },
            {
                "kind": "cylinder",
                "body_length_mm": 4.8,
                "body_width_mm": 4.8,
                "body_height_mm": 5.0,
                "pin_count": 0,
                "offset_mm": (0.0, 29.0, 0.0),
                "body_name": "shaft",
            },
        ],
    },
    "actuator-relay-generic": {
        "outline": "SRD relay (representative)",
        "source": "Songle SRD-05VDC-SL-C (19.1 x 15.5 x 15.3 mm, 5 pins)",
        "note": "Generic module: relay only; module PCB and terminals vary "
        "by vendor.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 19.1,
                "body_width_mm": 15.5,
                "body_height_mm": 15.3,
                "pin_count": 0,
                "body_name": "body",
            },
        ],
    },
}

VISUAL_SPECS: dict[str, tuple[ProceduralSpec, ...]] = {
    component_id: tuple(ProceduralSpec.model_validate(solid) for solid in row["solids"])
    for component_id, row in PART_VISUALS.items()
}


PACK_ID = "iot"
PACK_VERSION = "2.0.0"
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
        symbol="mcu",
    ),
    EntityTypeDef(
        "sensor-module",
        "Sensor module",
        "sensor",
        ("sensor", "temperature", "humidity", "pressure", "accelerometer", "dht", "bme"),
        (power_iface(), data_iface()),
        identity_keys=("model", "part"),
        symbol="sensor",
    ),
    EntityTypeDef(
        "actuator",
        "Actuator",
        "compute",
        ("actuator", "relay", "motor", "servo", "valve"),
        (power_iface(), InterfaceDef("control", "signal")),
        symbol="actuator",
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
        symbol="radio",
    ),
    EntityTypeDef(
        "cloud-service",
        "Cloud service",
        "network",
        ("cloud", "dashboard", "server", "mqtt broker", "backend", "api"),
        (InterfaceDef("api", "protocol"),),
        physical=False,
        symbol="cloud",
    ),
    EntityTypeDef(
        "power-supply",
        "Power supply",
        "power",
        ("battery", "power supply", "solar", "charger", "regulator"),
        (power_iface(),),
        symbol="supply",
    ),
)

# ---------------------------------------------------------------------------
# Link preflight: candidate config schema plus GPIO distinctness.
# ---------------------------------------------------------------------------

#: Payload config keys that may name the candidate part.
_IDENTITY_KEYS = ("model", "part", "part_number")


def _match_candidate(
    entries: tuple[ComponentDetail, ...], config: dict[str, Any]
) -> ComponentDetail | None:
    """Return the catalog entry the payload config names, if any.

    Matches are exact part-number (or default-model) strings; anything
    else means the pack cannot verify the candidate, so the IoT rules
    stay silent and the lexical interface check still applies.
    """
    wanted = {
        str(config[key]).strip().lower()
        for key in _IDENTITY_KEYS
        if isinstance(config.get(key), str) and str(config[key]).strip()
    }
    if not wanted:
        return None
    for entry in entries:
        candidates = {str(entry.default_config.get("model", "")).strip().lower()}
        if entry.part_number:
            candidates.add(entry.part_number.strip().lower())
        if wanted & (candidates - {""}):
            return entry
    return None


def _type_matches(field_type: str, value: object) -> bool:
    """Return whether a config value fits one schema field type."""
    if field_type == "string":
        return isinstance(value, str)
    if field_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if field_type == "boolean":
        return isinstance(value, bool)
    if field_type == "enum":
        return isinstance(value, str)
    return True


def _schema_findings(
    entry: ComponentDetail, config: dict[str, Any]
) -> list[PackPreflightFinding]:
    """Validate required keys, types, and enum options (blocking)."""
    findings: list[PackPreflightFinding] = []
    fields: tuple[ConfigField, ...] = entry.config_schema
    for field in fields:
        if field.key not in config:
            if field.required:
                findings.append(
                    PackPreflightFinding(
                        rule_id="iot_config_required",
                        severity=PackPreflightSeverity.BLOCK,
                        message=(
                            f"{entry.label} requires '{field.key}' ({field.label}) "
                            "but the replacement config omits it."
                        ),
                    )
                )
            continue
        value = config[field.key]
        if not _type_matches(field.type, value):
            findings.append(
                PackPreflightFinding(
                    rule_id="iot_config_type",
                    severity=PackPreflightSeverity.BLOCK,
                    message=(
                        f"{entry.label} field '{field.key}' needs {field.type} "
                        f"but the replacement sets {value!r}."
                    ),
                )
            )
            continue
        if (
            field.type == "enum"
            and isinstance(value, str)
            and field.options
            and value not in field.options
        ):
            findings.append(
                PackPreflightFinding(
                    rule_id="iot_config_enum",
                    severity=PackPreflightSeverity.BLOCK,
                    message=(
                        f"{entry.label} field '{field.key}' must be one of "
                        f"{', '.join(field.options)} but the replacement sets {value!r}."
                    ),
                )
            )
    return findings


def _gpio_findings(
    entry: ComponentDetail, config: dict[str, Any]
) -> list[PackPreflightFinding]:
    """Block two pin roles sharing one GPIO number.

    Pack convention: config keys ending in ``_gpio`` denote distinct
    physical pin assignments, so any duplicate int assignment cannot
    work as wired.
    """
    seen: dict[int, str] = {}
    findings: list[PackPreflightFinding] = []
    for key in sorted(config):
        if not key.endswith("_gpio"):
            continue
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value in seen:
            findings.append(
                PackPreflightFinding(
                    rule_id="iot_gpio_distinct",
                    severity=PackPreflightSeverity.BLOCK,
                    message=(
                        f"{entry.label} assigns GPIO {value} to both "
                        f"'{seen[value]}' and '{key}'; each role needs its own pin."
                    ),
                )
            )
        else:
            seen[value] = key
    return findings


class IoTPack:
    """Phase-9 IoT pack behind the DomainPack/ProfiledPack protocols.

    Everything delegates to the generic lexical harness except
    :meth:`check_patch`, which adds link preflight over the
    candidate's own config schema and GPIO assignments, and the
    render path, which serves per-part assemblies with part labels.
    """

    def __init__(self) -> None:
        self._lexical = LexicalPack(
            pack_id=PACK_ID,
            pack_version=PACK_VERSION,
            display=DISPLAY,
            signals=SIGNALS,
            threshold=THRESHOLD,
            entity_types=ENTITY_TYPES,
            catalog=COMPONENTS,
            simulator_adapter_ids=(),
        )

    @property
    def pack_id(self) -> str:
        """Return the stable pack identifier."""
        return self._lexical.pack_id

    @property
    def pack_version(self) -> str:
        """Return the exact pack version."""
        return self._lexical.pack_version

    @property
    def vocabulary(self) -> PackVocabulary:
        """Return the component vocabulary derived from pack entity types."""
        return self._lexical.vocabulary

    @property
    def simulator_adapter_ids(self) -> tuple[str, ...]:
        """Return adapter ids this pack can run."""
        return self._lexical.simulator_adapter_ids

    @property
    def copilot_tools(self) -> tuple[CopilotToolSpec, ...]:
        """Return the pack-provided tools the copilot may call."""
        return self._lexical.copilot_tools

    @property
    def profile(self) -> DomainProfile:
        """Return the detection signals and entity types this pack handles."""
        return self._lexical.profile

    @property
    def catalog_entries(self) -> tuple[ComponentDetail, ...]:
        """Return the validated catalog entries this pack contributes."""
        return self._lexical.catalog_entries

    def detect(self, tags: tuple[DomainTag, ...]) -> float:
        """Score pack affinity: matched signals over the open-vocabulary tags."""
        return self._lexical.detect(tags)

    def resolve_part(self, ref: PartRef) -> PartResolution:
        """Resolve one part mention down the exact/family/category ladder."""
        return self._lexical.resolve_part(ref)

    def render_spec(self, resolution: PartResolution) -> RenderSpec:
        """Label modeled parts with the part name and visual outline."""
        base = self._lexical.render_spec(resolution)
        if resolution.asset_key is None or resolution.asset_key not in PART_VISUALS:
            return base
        entry = next(
            (
                candidate
                for candidate in self.catalog_entries
                if candidate.component_id == resolution.asset_key
            ),
            None,
        )
        if entry is None:  # pragma: no cover - visual keys mirror the catalog
            return base
        outline = PART_VISUALS[resolution.asset_key]["outline"]
        return base.model_copy(update={"label": entry.label, "fallback_package": outline})

    def procedural_spec(
        self, node_config: Mapping[str, Any], resolution: PartResolution
    ) -> tuple[ProceduralSpec, ...]:
        """Return the part assembly for one modeled part, or () otherwise."""
        if resolution.asset_key is None:
            return ()
        return VISUAL_SPECS.get(resolution.asset_key, ())

    def check_patch(
        self, graph: MethodologyGraph, patch: GraphPatch
    ) -> tuple[PackPreflightFinding, ...]:
        """Block interface-dropping swaps and invalid link configs."""
        lexical = self._lexical.check_patch(graph, patch)
        if patch.operation is not PatchOperation.REPLACE_NODE:
            return lexical
        target = next((node for node in graph.nodes if node.id == patch.target_id), None)
        payload_node = patch.payload.get("node")
        if target is None or not isinstance(payload_node, dict):
            return lexical
        try:
            candidate = GraphNode.model_validate(payload_node)
        except ValidationError:
            return lexical
        entry = _match_candidate(self.catalog_entries, dict(candidate.config))
        if entry is None:
            return lexical
        config = dict(candidate.config)
        rules = (*_schema_findings(entry, config), *_gpio_findings(entry, config))
        return (*lexical, *rules)

    def simulation_preview(self, graph: MethodologyGraph) -> SimulationPreview | None:
        """Return the wired builder's preview, or None when the pack offers none."""
        return self._lexical.simulation_preview(graph)

    def telemetry_mapping(self) -> TelemetryMapping | None:
        """Return None: no pack maps live telemetry yet (Stage 2)."""
        return self._lexical.telemetry_mapping()


pack = IoTPack()
