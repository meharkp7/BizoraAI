"""Electronics pack data: catalog entries plus detection profile.

Moved verbatim from the former core registry: part names, signals, and
match terms live here as data, and the generic pack harness interprets
them without per-part branches.
"""

from typing import Any

from bizora.contracts.assets import ProceduralSpec
from bizora.core.entity_registry import EntityTypeDef, InterfaceDef
from bizora.packs.lexical import data_iface, power_iface

POWER = {"name": "power", "kind": "power", "params": {}}
DATA = {"name": "data", "kind": "data", "params": {}}
SIGNAL = {"name": "signal", "kind": "signal", "params": {}}
ANALOG_IN = {"name": "in", "kind": "analog", "params": {}}
ANALOG_OUT = {"name": "out", "kind": "analog", "params": {}}

COMPONENTS: list[dict[str, Any]] = [
    {
        "component_id": "npn-2n3904",
        "domain": "electronics",
        "entity_type": "transistor",
        "category": "discrete",
        "kind": "component",
        "label": "2N3904 NPN transistor",
        "generic": False,
        "manufacturer": "onsemi",
        "part_number": "2N3904",
        "headline": "NPN general-purpose amplifier, 40 V / 200 mA, TO-92",
        "description": (
            "2N3904 NPN general-purpose transistor for switching and small-signal "
            "amplification. Drop-in NPN where collector current stays under 200 mA."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Polarity", "value": "NPN", "typical": False},
            {
                "name": "Collector-emitter voltage (max)",
                "value": "40",
                "unit": "V",
                "typical": False,
            },
            {"name": "Collector current (max)", "value": "200", "unit": "mA", "typical": False},
            {"name": "DC current gain", "value": "100-400", "typical": True},
            {"name": "Transition frequency", "value": "300", "unit": "MHz", "typical": True},
            {"name": "Package", "value": "TO-92", "typical": False},
        ],
        "pinout": [
            {"designator": "1", "name": "Emitter", "function": "NPN emitter terminal"},
            {"designator": "2", "name": "Base", "function": "Control terminal"},
            {"designator": "3", "name": "Collector", "function": "NPN collector terminal"},
        ],
        "interfaces": [
            POWER,
            {"name": "gate", "kind": "signal", "params": {}},
            {"name": "channel", "kind": "signal", "params": {}},
        ],
        "constraints": {"max_current_mA": "200", "max_voltage_V": "40"},
        "config_schema": [
            {
                "key": "part",
                "label": "Part number",
                "type": "string",
                "default": "2N3904",
                "required": True,
                "description": "Exact manufacturer part number.",
            },
            {
                "key": "package",
                "label": "Package",
                "type": "enum",
                "default": "TO-92",
                "options": ["TO-92", "SOT-23"],
                "required": False,
                "description": "Package variant; pinout follows the package drawing.",
            },
        ],
        "default_config": {"part": "2N3904", "device": "NPN", "package": "TO-92"},
        "evidence": [
            {"source": "onsemi 2N3904 datasheet (2N3903/D)", "note": "Electrical ratings."},
        ],
    },
    {
        "component_id": "npn-bc547",
        "domain": "electronics",
        "entity_type": "transistor",
        "category": "discrete",
        "kind": "component",
        "label": "BC547 NPN transistor",
        "generic": False,
        "manufacturer": "onsemi",
        "part_number": "BC547",
        "headline": "NPN general-purpose transistor, 45 V / 100 mA, TO-92",
        "description": (
            "BC547 NPN transistor for low-power switching and amplification. "
            "Note the C-B-E pin order, which differs from the 2N3904 E-B-C order."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Polarity", "value": "NPN", "typical": False},
            {
                "name": "Collector-emitter voltage (max)",
                "value": "45",
                "unit": "V",
                "typical": False,
            },
            {"name": "Collector current (max)", "value": "100", "unit": "mA", "typical": False},
            {"name": "DC current gain", "value": "110-800", "typical": True},
            {"name": "Package", "value": "TO-92", "typical": False},
        ],
        "pinout": [
            {"designator": "1", "name": "Collector", "function": "NPN collector terminal"},
            {"designator": "2", "name": "Base", "function": "Control terminal"},
            {"designator": "3", "name": "Emitter", "function": "NPN emitter terminal"},
        ],
        "interfaces": [
            POWER,
            {"name": "gate", "kind": "signal", "params": {}},
            {"name": "channel", "kind": "signal", "params": {}},
        ],
        "constraints": {"max_current_mA": "100", "max_voltage_V": "45"},
        "config_schema": [
            {
                "key": "part",
                "label": "Part number",
                "type": "string",
                "default": "BC547",
                "required": True,
                "description": "Exact manufacturer part number.",
            },
            {
                "key": "gain_group",
                "label": "Gain group",
                "type": "enum",
                "default": "B",
                "options": ["A", "B", "C"],
                "required": False,
                "description": "hFE selection group printed on the device.",
            },
        ],
        "default_config": {"part": "BC547", "device": "NPN", "package": "TO-92"},
        "evidence": [{"source": "onsemi BC547 datasheet", "note": "Electrical ratings."}],
    },
    {
        "component_id": "nmos-irf540n",
        "domain": "electronics",
        "entity_type": "transistor",
        "category": "discrete",
        "kind": "component",
        "label": "IRF540N N-channel MOSFET",
        "generic": False,
        "manufacturer": "Infineon",
        "part_number": "IRF540N",
        "headline": "N-channel power MOSFET, 100 V / 33 A, TO-220",
        "description": (
            "IRF540N N-channel power MOSFET for switching loads up to 33 A. "
            "Logic-level gate drive is marginal; prefer a 10 V gate driver."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Channel", "value": "N", "typical": False},
            {"name": "Drain-source voltage (max)", "value": "100", "unit": "V", "typical": False},
            {"name": "Drain current (max)", "value": "33", "unit": "A", "typical": False},
            {"name": "On resistance", "value": "44", "unit": "mΩ", "typical": True},
            {"name": "Gate threshold", "value": "2-4", "unit": "V", "typical": True},
            {"name": "Package", "value": "TO-220", "typical": False},
        ],
        "pinout": [
            {"designator": "1", "name": "Gate", "function": "Control terminal"},
            {"designator": "2", "name": "Drain", "function": "Switched terminal (tab connected)"},
            {"designator": "3", "name": "Source", "function": "Reference terminal"},
        ],
        "interfaces": [
            POWER,
            {"name": "gate", "kind": "signal", "params": {}},
            {"name": "channel", "kind": "signal", "params": {}},
        ],
        "constraints": {"max_current_mA": "33000", "max_voltage_V": "100"},
        "config_schema": [
            {
                "key": "part",
                "label": "Part number",
                "type": "string",
                "default": "IRF540N",
                "required": True,
                "description": "Exact manufacturer part number.",
            },
            {
                "key": "gate_drive_V",
                "label": "Gate drive voltage",
                "type": "number",
                "default": 10,
                "unit": "V",
                "required": False,
                "description": "Gate-source drive voltage used in this design.",
            },
        ],
        "default_config": {"part": "IRF540N", "device": "NMOS", "package": "TO-220"},
        "evidence": [{"source": "Infineon IRF540N datasheet", "note": "Electrical ratings."}],
    },
    {
        "component_id": "nmos-2n7000",
        "domain": "electronics",
        "entity_type": "transistor",
        "category": "discrete",
        "kind": "component",
        "label": "2N7000 N-channel MOSFET",
        "generic": False,
        "manufacturer": "onsemi",
        "part_number": "2N7000",
        "headline": "N-channel small-signal MOSFET, 60 V / 200 mA, TO-92",
        "description": (
            "2N7000 small-signal N-channel MOSFET for low-current switching. "
            "Pin order is S-G-D, which differs from bipolar TO-92 parts."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Channel", "value": "N", "typical": False},
            {"name": "Drain-source voltage (max)", "value": "60", "unit": "V", "typical": False},
            {"name": "Drain current (max)", "value": "200", "unit": "mA", "typical": False},
            {"name": "On resistance", "value": "5", "unit": "Ω", "typical": True},
            {"name": "Package", "value": "TO-92", "typical": False},
        ],
        "pinout": [
            {"designator": "1", "name": "Source", "function": "Reference terminal"},
            {"designator": "2", "name": "Gate", "function": "Control terminal"},
            {"designator": "3", "name": "Drain", "function": "Switched terminal"},
        ],
        "interfaces": [
            POWER,
            {"name": "gate", "kind": "signal", "params": {}},
            {"name": "channel", "kind": "signal", "params": {}},
        ],
        "constraints": {"max_current_mA": "200", "max_voltage_V": "60"},
        "config_schema": [
            {
                "key": "part",
                "label": "Part number",
                "type": "string",
                "default": "2N7000",
                "required": True,
                "description": "Exact manufacturer part number.",
            },
        ],
        "default_config": {"part": "2N7000", "device": "NMOS", "package": "TO-92"},
        "evidence": [{"source": "onsemi 2N7000 datasheet", "note": "Electrical ratings."}],
    },
    {
        "component_id": "mosfet-nmos-generic",
        "domain": "electronics",
        "entity_type": "transistor",
        "category": "discrete",
        "kind": "component",
        "label": "NMOS transistor (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Correctly identified generic N-channel MOSFET, no exact part",
        "description": (
            "Generic N-channel MOSFET placeholder for schematics that do not name an "
            "exact part. Replace with an exact MOSFET before simulation or layout."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Channel", "value": "N", "typical": False},
            {"name": "Identity", "value": "generic", "typical": False},
        ],
        "pinout": [
            {"designator": "G", "name": "Gate", "function": "Control terminal"},
            {"designator": "D", "name": "Drain", "function": "Switched terminal"},
            {"designator": "S", "name": "Source", "function": "Reference terminal"},
        ],
        "interfaces": [
            POWER,
            {"name": "gate", "kind": "signal", "params": {}},
            {"name": "channel", "kind": "signal", "params": {}},
        ],
        "constraints": {},
        "config_schema": [
            {
                "key": "device",
                "label": "Device",
                "type": "string",
                "default": "NMOS",
                "required": True,
                "description": "Device family recorded on the node.",
            },
        ],
        "default_config": {"device": "NMOS"},
        "evidence": [],
    },
    {
        "component_id": "mosfet-pmos-generic",
        "domain": "electronics",
        "entity_type": "transistor",
        "category": "discrete",
        "kind": "component",
        "label": "PMOS transistor (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Correctly identified generic P-channel MOSFET, no exact part",
        "description": (
            "Generic P-channel MOSFET placeholder for schematics that do not name an "
            "exact part. Replace with an exact MOSFET before simulation or layout."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Channel", "value": "P", "typical": False},
            {"name": "Identity", "value": "generic", "typical": False},
        ],
        "pinout": [
            {"designator": "G", "name": "Gate", "function": "Control terminal"},
            {"designator": "D", "name": "Drain", "function": "Switched terminal"},
            {"designator": "S", "name": "Source", "function": "Reference terminal"},
        ],
        "interfaces": [
            POWER,
            {"name": "gate", "kind": "signal", "params": {}},
            {"name": "channel", "kind": "signal", "params": {}},
        ],
        "constraints": {},
        "config_schema": [
            {
                "key": "device",
                "label": "Device",
                "type": "string",
                "default": "PMOS",
                "required": True,
                "description": "Device family recorded on the node.",
            },
        ],
        "default_config": {"device": "PMOS"},
        "evidence": [],
    },
    {
        "component_id": "diode-1n4148",
        "domain": "electronics",
        "entity_type": "diode",
        "category": "discrete",
        "kind": "component",
        "label": "1N4148 switching diode",
        "generic": False,
        "manufacturer": "multi-source",
        "part_number": "1N4148",
        "headline": "Fast switching diode, 100 V / 200 mA, DO-35",
        "description": (
            "1N4148 small-signal switching diode, second-sourced across manufacturers. "
            "Standard choice for clamping, steering, and reverse-polarity protection."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Reverse voltage (max)", "value": "100", "unit": "V", "typical": False},
            {"name": "Forward current (max)", "value": "200", "unit": "mA", "typical": False},
            {"name": "Forward voltage", "value": "0.7", "unit": "V", "typical": True},
            {"name": "Reverse recovery", "value": "4", "unit": "ns", "typical": True},
            {"name": "Package", "value": "DO-35", "typical": False},
        ],
        "pinout": [
            {"designator": "A", "name": "Anode", "function": "Forward-current input"},
            {"designator": "K", "name": "Cathode", "function": "Banded terminal"},
        ],
        "interfaces": [
            {"name": "anode", "kind": "signal", "params": {}},
            {"name": "cathode", "kind": "signal", "params": {}},
        ],
        "constraints": {"max_current_mA": "200", "max_voltage_V": "100"},
        "config_schema": [
            {
                "key": "part",
                "label": "Part number",
                "type": "string",
                "default": "1N4148",
                "required": True,
                "description": "Exact part number.",
            },
        ],
        "default_config": {"part": "1N4148"},
        "evidence": [{"source": "Multi-source 1N4148 datasheet", "note": "JEDEC-registered part."}],
    },
    {
        "component_id": "ic-ne555",
        "domain": "electronics",
        "entity_type": "analog-ic",
        "category": "package",
        "kind": "component",
        "label": "NE555 precision timer",
        "generic": False,
        "manufacturer": "Texas Instruments",
        "part_number": "NE555",
        "headline": "Precision timer IC, 4.5-16 V supply, 8-pin",
        "description": (
            "NE555 monolithic timer for delay generation and oscillation. "
            "Astable frequency is set by two resistors and one capacitor."
        ),
        "datasheet_url": None,
        "reference_url": "https://www.ti.com/product/NE555",
        "specs": [
            {"name": "Supply range", "value": "4.5-16", "unit": "V", "typical": False},
            {"name": "Output current (max)", "value": "200", "unit": "mA", "typical": False},
            {"name": "Timing range", "value": "microseconds to hours", "typical": True},
            {"name": "Package", "value": "PDIP-8 / SOIC-8", "typical": False},
        ],
        "pinout": [
            {"designator": "1", "name": "GND", "function": "Ground"},
            {"designator": "2", "name": "TRIG", "function": "Trigger input"},
            {"designator": "3", "name": "OUT", "function": "Timer output"},
            {"designator": "4", "name": "RESET", "function": "Active-low reset"},
            {"designator": "5", "name": "CONT", "function": "Control voltage"},
            {"designator": "6", "name": "THRES", "function": "Threshold input"},
            {"designator": "7", "name": "DISCH", "function": "Discharge transistor"},
            {"designator": "8", "name": "VCC", "function": "Positive supply"},
        ],
        "interfaces": [POWER, ANALOG_IN, ANALOG_OUT],
        "constraints": {"supply_min_V": "4.5", "supply_max_V": "16"},
        "config_schema": [
            {
                "key": "part",
                "label": "Part number",
                "type": "string",
                "default": "NE555",
                "required": True,
                "description": "Exact manufacturer part number.",
            },
            {
                "key": "mode",
                "label": "Mode",
                "type": "enum",
                "default": "astable",
                "options": ["astable", "monostable", "bistable"],
                "required": True,
                "description": "Timer operating mode.",
            },
            {
                "key": "frequency_hz",
                "label": "Target frequency",
                "type": "number",
                "default": 1000,
                "unit": "Hz",
                "required": False,
                "description": "Target output frequency for astable mode.",
            },
        ],
        "default_config": {"part": "NE555", "mode": "astable"},
        "evidence": [
            {
                "source": "TI NE555 product page",
                "note": "Verified reference URL; consult the datasheet for limits.",
            },
        ],
    },
    {
        "component_id": "ic-lm358",
        "domain": "electronics",
        "entity_type": "analog-ic",
        "category": "package",
        "kind": "component",
        "label": "LM358 dual operational amplifier",
        "generic": False,
        "manufacturer": "Texas Instruments",
        "part_number": "LM358",
        "headline": "Dual op-amp, 3-32 V single supply, 8-pin",
        "description": (
            "LM358 dual operational amplifier for single-supply sensing and "
            "conditioning circuits such as current monitors and comparators."
        ),
        "datasheet_url": None,
        "reference_url": "https://www.ti.com/product/LM358",
        "specs": [
            {"name": "Supply range", "value": "3-32", "unit": "V", "typical": False},
            {"name": "Input offset", "value": "2", "unit": "mV", "typical": True},
            {"name": "Gain-bandwidth", "value": "1", "unit": "MHz", "typical": True},
            {"name": "Channels", "value": "2", "typical": False},
        ],
        "pinout": [
            {"designator": "1", "name": "OUT1", "function": "Channel 1 output"},
            {"designator": "2", "name": "IN1-", "function": "Channel 1 inverting input"},
            {"designator": "3", "name": "IN1+", "function": "Channel 1 non-inverting input"},
            {"designator": "4", "name": "VEE/GND", "function": "Negative supply or ground"},
            {"designator": "5", "name": "IN2+", "function": "Channel 2 non-inverting input"},
            {"designator": "6", "name": "IN2-", "function": "Channel 2 inverting input"},
            {"designator": "7", "name": "OUT2", "function": "Channel 2 output"},
            {"designator": "8", "name": "VCC", "function": "Positive supply"},
        ],
        "interfaces": [POWER, ANALOG_IN, ANALOG_OUT],
        "constraints": {"supply_min_V": "3", "supply_max_V": "32"},
        "config_schema": [
            {
                "key": "part",
                "label": "Part number",
                "type": "string",
                "default": "LM358",
                "required": True,
                "description": "Exact manufacturer part number.",
            },
            {
                "key": "gain",
                "label": "Closed-loop gain",
                "type": "number",
                "default": 1,
                "required": False,
                "description": "Configured closed-loop voltage gain.",
            },
        ],
        "default_config": {"part": "LM358"},
        "evidence": [
            {
                "source": "TI LM358 product page",
                "note": "Verified reference URL; consult the datasheet for limits.",
            },
        ],
    },
    {
        "component_id": "logic-74hc04",
        "domain": "electronics",
        "entity_type": "logic-gate",
        "category": "package",
        "kind": "component",
        "label": "SN74HC04 hex inverter",
        "generic": False,
        "manufacturer": "Texas Instruments",
        "part_number": "SN74HC04",
        "headline": "Hex CMOS inverter, 2-6 V supply, 14-pin",
        "description": (
            "SN74HC04 hex inverter for buffering and oscillator duty in 5 V and "
            "3.3 V logic. Unused inputs must be tied to VCC or GND."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Supply range", "value": "2-6", "unit": "V", "typical": False},
            {"name": "Gates", "value": "6", "typical": False},
            {"name": "Output current", "value": "5.2", "unit": "mA", "typical": True},
            {"name": "Package", "value": "SOIC-14 / TSSOP-14", "typical": False},
        ],
        "pinout": [
            {"designator": "1", "name": "1A", "function": "Gate 1 input"},
            {"designator": "2", "name": "1Y", "function": "Gate 1 output"},
            {"designator": "3", "name": "2A", "function": "Gate 2 input"},
            {"designator": "4", "name": "2Y", "function": "Gate 2 output"},
            {"designator": "5", "name": "3A", "function": "Gate 3 input"},
            {"designator": "6", "name": "3Y", "function": "Gate 3 output"},
            {"designator": "7", "name": "GND", "function": "Ground"},
            {"designator": "8", "name": "4Y", "function": "Gate 4 output"},
            {"designator": "9", "name": "4A", "function": "Gate 4 input"},
            {"designator": "10", "name": "5Y", "function": "Gate 5 output"},
            {"designator": "11", "name": "5A", "function": "Gate 5 input"},
            {"designator": "12", "name": "6Y", "function": "Gate 6 output"},
            {"designator": "13", "name": "6A", "function": "Gate 6 input"},
            {"designator": "14", "name": "VCC", "function": "Positive supply"},
        ],
        "interfaces": [POWER, DATA],
        "constraints": {"supply_min_V": "2", "supply_max_V": "6"},
        "config_schema": [
            {
                "key": "part",
                "label": "Part number",
                "type": "string",
                "default": "SN74HC04",
                "required": True,
                "description": "Exact manufacturer part number.",
            },
            {
                "key": "supply_V",
                "label": "Supply voltage",
                "type": "number",
                "default": 5,
                "unit": "V",
                "required": True,
                "description": "Logic supply rail in this design.",
            },
        ],
        "default_config": {"part": "SN74HC04", "supply_V": 5},
        "evidence": [{"source": "TI SN74HC04 datasheet", "note": "Pinout and ratings."}],
    },
    {
        "component_id": "logic-gate-generic",
        "domain": "electronics",
        "entity_type": "logic-gate",
        "category": "package",
        "kind": "component",
        "label": "Logic gate (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Correctly identified generic logic gate, no exact part",
        "description": (
            "Generic logic-gate placeholder where the schematic names no exact family "
            "or part. Pin down the family (HC, LVC, ...) before interfacing."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [POWER, DATA],
        "constraints": {},
        "config_schema": [],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "reg-lm7805",
        "domain": "electronics",
        "entity_type": "voltage-source",
        "category": "power",
        "kind": "component",
        "label": "LM7805 5 V linear regulator",
        "generic": False,
        "manufacturer": "onsemi",
        "part_number": "MC7805",
        "headline": "5 V linear regulator, 1 A, TO-220",
        "description": (
            "LM7805-series 5 V linear regulator (onsemi MC7805) for logic rails up to "
            "1 A with adequate heatsinking. Dropout is about 2 V."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Output", "value": "5", "unit": "V", "typical": False},
            {"name": "Output current (max)", "value": "1", "unit": "A", "typical": False},
            {"name": "Dropout", "value": "2", "unit": "V", "typical": True},
            {"name": "Package", "value": "TO-220", "typical": False},
        ],
        "pinout": [
            {"designator": "1", "name": "Input", "function": "Unregulated input"},
            {"designator": "2", "name": "GND", "function": "Ground (tab connected)"},
            {"designator": "3", "name": "Output", "function": "Regulated 5 V output"},
        ],
        "interfaces": [POWER],
        "constraints": {"supply_min_V": "7", "supply_max_V": "25"},
        "config_schema": [
            {
                "key": "part",
                "label": "Part number",
                "type": "string",
                "default": "MC7805",
                "required": True,
                "description": "Exact manufacturer part number.",
            },
            {
                "key": "output_V",
                "label": "Output voltage",
                "type": "number",
                "default": 5,
                "unit": "V",
                "required": True,
                "description": "Regulated output rail.",
            },
        ],
        "default_config": {"part": "MC7805", "output_V": 5},
        "evidence": [{"source": "onsemi MC7800 datasheet", "note": "Electrical ratings."}],
    },
    {
        "component_id": "psu-vdd-generic",
        "domain": "electronics",
        "entity_type": "voltage-source",
        "category": "power",
        "kind": "component",
        "label": "VDD supply rail (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Ideal supply rail placeholder with a settable voltage",
        "description": (
            "Generic ideal supply rail for schematics that name no regulator or "
            "source. Set the rail voltage; replace with an exact regulator for builds."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [{"designator": "VDD", "name": "VDD", "function": "Positive rail"}],
        "interfaces": [POWER],
        "constraints": {},
        "config_schema": [
            {
                "key": "supply_V",
                "label": "Rail voltage",
                "type": "number",
                "default": 3.3,
                "unit": "V",
                "required": True,
                "description": "Nominal rail voltage.",
            },
        ],
        "default_config": {"supply_V": 3.3},
        "evidence": [],
    },
    {
        "component_id": "sense-ina219",
        "domain": "electronics",
        "entity_type": "measurement",
        "category": "sensor",
        "kind": "component",
        "label": "INA219 current and power monitor",
        "generic": False,
        "manufacturer": "Texas Instruments",
        "part_number": "INA219",
        "headline": "Bidirectional current/power monitor, I2C, 26 V bus",
        "description": (
            "INA219 high-side current and power monitor with an I2C readout. "
            "Standard choice for supply-rail telemetry and leakage characterization."
        ),
        "datasheet_url": None,
        "reference_url": "https://www.ti.com/product/INA219",
        "specs": [
            {"name": "Bus range", "value": "0-26", "unit": "V", "typical": False},
            {"name": "Interface", "value": "I2C", "typical": False},
            {"name": "Current resolution", "value": "0.8", "unit": "mA", "typical": True},
            {"name": "Supply", "value": "3-5.5", "unit": "V", "typical": False},
            {"name": "Package", "value": "SOIC-8", "typical": False},
        ],
        "pinout": [
            {"designator": "A0", "name": "A0", "function": "I2C address bit 0"},
            {"designator": "A1", "name": "A1", "function": "I2C address bit 1"},
            {"designator": "SCL", "name": "SCL", "function": "I2C clock"},
            {"designator": "SDA", "name": "SDA", "function": "I2C data"},
            {"designator": "VS", "name": "VS", "function": "Supply voltage"},
            {"designator": "GND", "name": "GND", "function": "Ground"},
            {"designator": "VIN+", "name": "VIN+", "function": "Shunt high side"},
            {"designator": "VIN-", "name": "VIN-", "function": "Shunt low side"},
        ],
        "interfaces": [
            POWER,
            {"name": "sense", "kind": "analog", "params": {}},
        ],
        "constraints": {"supply_min_V": "3", "supply_max_V": "5.5"},
        "config_schema": [
            {
                "key": "part",
                "label": "Part number",
                "type": "string",
                "default": "INA219",
                "required": True,
                "description": "Exact manufacturer part number.",
            },
            {
                "key": "shunt_ohm",
                "label": "Shunt resistance",
                "type": "number",
                "default": 0.1,
                "unit": "Ω",
                "required": True,
                "description": "Current-sense shunt value on the board.",
            },
            {
                "key": "i2c_address",
                "label": "I2C address",
                "type": "string",
                "default": "0x40",
                "required": True,
                "description": "Seven-bit I2C address set by A0/A1.",
            },
        ],
        "default_config": {"part": "INA219", "shunt_ohm": 0.1, "i2c_address": "0x40"},
        "evidence": [
            {
                "source": "TI INA219 product page",
                "note": "Verified reference URL; consult the datasheet for limits.",
            },
        ],
    },
    {
        "component_id": "adc-ads1115",
        "domain": "electronics",
        "entity_type": "data-converter",
        "category": "package",
        "kind": "component",
        "label": "ADS1115 16-bit ADC",
        "generic": False,
        "manufacturer": "Texas Instruments",
        "part_number": "ADS1115",
        "headline": "16-bit I2C ADC, 4 channels, programmable gain",
        "description": (
            "ADS1115 precision 16-bit analog-to-digital converter with four "
            "single-ended channels and an I2C interface for slow telemetry."
        ),
        "datasheet_url": None,
        "reference_url": "https://www.ti.com/product/ADS1115",
        "specs": [
            {"name": "Resolution", "value": "16", "unit": "bit", "typical": False},
            {"name": "Channels", "value": "4", "typical": False},
            {"name": "Interface", "value": "I2C", "typical": False},
            {"name": "Supply", "value": "2-5.5", "unit": "V", "typical": False},
        ],
        "pinout": [
            {"designator": "VDD", "name": "VDD", "function": "Supply voltage"},
            {"designator": "GND", "name": "GND", "function": "Ground"},
            {"designator": "SCL", "name": "SCL", "function": "I2C clock"},
            {"designator": "SDA", "name": "SDA", "function": "I2C data"},
            {"designator": "ADDR", "name": "ADDR", "function": "I2C address select"},
            {"designator": "A0", "name": "A0", "function": "Analog input 0"},
            {"designator": "A1", "name": "A1", "function": "Analog input 1"},
            {"designator": "A2", "name": "A2", "function": "Analog input 2"},
            {"designator": "A3", "name": "A3", "function": "Analog input 3"},
        ],
        "interfaces": [POWER, {"name": "analog", "kind": "analog", "params": {}}, DATA],
        "constraints": {"supply_min_V": "2", "supply_max_V": "5.5"},
        "config_schema": [
            {
                "key": "part",
                "label": "Part number",
                "type": "string",
                "default": "ADS1115",
                "required": True,
                "description": "Exact manufacturer part number.",
            },
            {
                "key": "gain",
                "label": "PGA gain",
                "type": "enum",
                "default": "1",
                "options": ["0.67", "1", "2", "4", "8", "16"],
                "required": True,
                "description": "Programmable gain setting.",
            },
            {
                "key": "data_rate_sps",
                "label": "Data rate",
                "type": "number",
                "default": 128,
                "unit": "SPS",
                "required": False,
                "description": "Output data rate in samples per second.",
            },
        ],
        "default_config": {"part": "ADS1115", "gain": "1"},
        "evidence": [
            {
                "source": "TI ADS1115 product page",
                "note": "Verified reference URL; consult the datasheet for limits.",
            },
        ],
    },
    {
        "component_id": "current-sense-generic",
        "domain": "electronics",
        "entity_type": "measurement",
        "category": "sensor",
        "kind": "component",
        "label": "Current monitor (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Correctly identified generic current monitor, no exact part",
        "description": (
            "Generic current-measurement element where the schematic names no exact "
            "monitor IC. Replace with an INA219-class part for real telemetry."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [POWER, {"name": "sense", "kind": "analog", "params": {}}],
        "constraints": {},
        "config_schema": [],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "resistor-generic",
        "domain": "electronics",
        "entity_type": "passive",
        "category": "passive",
        "kind": "component",
        "label": "Resistor (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic resistor with settable resistance and footprint",
        "description": (
            "Correctly identified generic resistor. Set the resistance and footprint; "
            "no exact manufacturer part is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [
            {"designator": "1", "name": "Terminal 1", "function": None},
            {"designator": "2", "name": "Terminal 2", "function": None},
        ],
        "interfaces": [POWER],
        "constraints": {},
        "config_schema": [
            {
                "key": "resistance_ohm",
                "label": "Resistance",
                "type": "number",
                "default": 10000,
                "unit": "Ω",
                "required": True,
                "description": "Nominal resistance.",
            },
            {
                "key": "footprint",
                "label": "Footprint",
                "type": "enum",
                "default": "0603",
                "options": ["0402", "0603", "0805", "1206", "through-hole"],
                "required": False,
                "description": "Package footprint.",
            },
        ],
        "default_config": {"resistance_ohm": 10000, "footprint": "0603"},
        "evidence": [],
    },
    {
        "component_id": "capacitor-generic",
        "domain": "electronics",
        "entity_type": "passive",
        "category": "passive",
        "kind": "component",
        "label": "Capacitor (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic capacitor with settable capacitance and dielectric",
        "description": (
            "Correctly identified generic capacitor. Set the capacitance and "
            "dielectric; no exact manufacturer part is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [
            {"designator": "1", "name": "Terminal 1", "function": None},
            {"designator": "2", "name": "Terminal 2", "function": None},
        ],
        "interfaces": [POWER],
        "constraints": {},
        "config_schema": [
            {
                "key": "capacitance_uF",
                "label": "Capacitance",
                "type": "number",
                "default": 0.1,
                "unit": "µF",
                "required": True,
                "description": "Nominal capacitance.",
            },
            {
                "key": "dielectric",
                "label": "Dielectric",
                "type": "enum",
                "default": "X7R",
                "options": ["X7R", "C0G", "X5R", "electrolytic", "film"],
                "required": False,
                "description": "Capacitor dielectric or construction.",
            },
        ],
        "default_config": {"capacitance_uF": 0.1, "dielectric": "X7R"},
        "evidence": [],
    },
    {
        "component_id": "sram-6t-generic",
        "domain": "electronics",
        "entity_type": "memory-cell",
        "category": "package",
        "kind": "component",
        "label": "6T SRAM bitcell (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic six-transistor SRAM storage cell",
        "description": (
            "Generic 6T SRAM bitcell: cross-coupled inverters plus two access "
            "transistors. Used for aging and stability studies without a foundry PDK."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Cell type", "value": "6T SRAM", "typical": False},
            {"name": "Identity", "value": "generic", "typical": False},
        ],
        "pinout": [
            {"designator": "WL", "name": "Wordline", "function": "Row select"},
            {"designator": "BL", "name": "Bitline", "function": "Data bit"},
            {"designator": "BLB", "name": "Bitline bar", "function": "Complementary data"},
            {"designator": "VDD", "name": "VDD", "function": "Cell supply"},
        ],
        "interfaces": [POWER, DATA],
        "constraints": {},
        "config_schema": [
            {
                "key": "cell_type",
                "label": "Cell type",
                "type": "string",
                "default": "6T SRAM",
                "required": True,
                "description": "Recorded cell topology.",
            },
        ],
        "default_config": {"cell_type": "6T SRAM"},
        "evidence": [],
    },
    {
        "component_id": "sense-amp-generic",
        "domain": "electronics",
        "entity_type": "sense-amplifier",
        "category": "package",
        "kind": "component",
        "label": "Sense amplifier (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic SRAM sense amplifier",
        "description": (
            "Generic sense amplifier for reading SRAM bitline state. "
            "No exact circuit topology is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [POWER, DATA, {"name": "sense", "kind": "analog", "params": {}}],
        "constraints": {},
        "config_schema": [],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "body-bias-generic",
        "domain": "electronics",
        "entity_type": "bias-controller",
        "category": "package",
        "kind": "component",
        "label": "Body-bias controller (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic adaptive body-bias compensation block",
        "description": (
            "Generic body-bias controller for compensating aging-induced threshold "
            "shift. Set the bias range the controller may apply."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [POWER, {"name": "bias", "kind": "analog", "params": {}}],
        "constraints": {},
        "config_schema": [
            {
                "key": "bias_min_V",
                "label": "Minimum bias",
                "type": "number",
                "default": -0.5,
                "unit": "V",
                "required": False,
                "description": "Most negative body bias the controller may apply.",
            },
            {
                "key": "bias_max_V",
                "label": "Maximum bias",
                "type": "number",
                "default": 0.5,
                "unit": "V",
                "required": False,
                "description": "Most positive body bias the controller may apply.",
            },
        ],
        "default_config": {},
        "evidence": [],
    },
]


# ---------------------------------------------------------------------------
# Part visuals: per-part assemblies from package outlines.
# ---------------------------------------------------------------------------
#
# Each row models one catalog part as placed solids in millimetres.
# Dimensions come from the cited source; representative outlines (a
# part that ships in several packages modeled in its most common
# through-hole outline) say so in the outline and note. Rows validate
# at import so a bad dimension breaks loudly instead of rendering a
# wrong part.

PART_VISUALS: dict[str, dict[str, Any]] = {
    "ic-ne555": {
        "outline": "PDIP-8 (representative)",
        "source": "Renesas PDIP-8 300mil (9.52 x 6.35 x 3.30 mm, 2.54 mm pitch)",
        "note": "NE555 also ships in SOIC; PDIP-8 is the representative "
        "through-hole outline.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 9.52,
                "body_width_mm": 6.35,
                "body_height_mm": 3.3,
                "pin_count": 8,
                "pin_pitch_mm": 2.54,
                "pin_rows": 2,
                "pin_length_mm": 3.0,
                "body_name": "body",
            },
        ],
    },
    "ic-lm358": {
        "outline": "PDIP-8 (representative)",
        "source": "Renesas PDIP-8 300mil (9.52 x 6.35 x 3.30 mm, 2.54 mm pitch)",
        "note": "LM358 also ships in SOIC; PDIP-8 is the representative "
        "through-hole outline.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 9.52,
                "body_width_mm": 6.35,
                "body_height_mm": 3.3,
                "pin_count": 8,
                "pin_pitch_mm": 2.54,
                "pin_rows": 2,
                "pin_length_mm": 3.0,
                "body_name": "body",
            },
        ],
    },
    "logic-74hc04": {
        "outline": "PDIP-14 (representative)",
        "source": "PDIP-14 300mil (19.18 x 6.35 mm body, 2.54 mm pitch, "
        "nominal profile height)",
        "note": "74HC04 also ships in SOIC/TSSOP; PDIP-14 is the "
        "representative through-hole outline.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 19.18,
                "body_width_mm": 6.35,
                "body_height_mm": 4.0,
                "pin_count": 14,
                "pin_pitch_mm": 2.54,
                "pin_rows": 2,
                "pin_length_mm": 3.0,
                "body_name": "body",
            },
        ],
    },
    "reg-lm7805": {
        "outline": "TO-220",
        "source": "JEDEC TO-220AB (10.04-10.41 mm wide, 2.54 mm pitch)",
        "note": "Tab hole omitted; Z-long orientation with centered leads.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 4.6,
                "body_width_mm": 10.2,
                "body_height_mm": 9.0,
                "pin_count": 3,
                "pin_pitch_mm": 2.54,
                "pin_rows": 3,
                "pin_length_mm": 5.0,
                "body_name": "body",
            },
            {
                "kind": "box",
                "body_length_mm": 1.4,
                "body_width_mm": 10.2,
                "body_height_mm": 6.0,
                "pin_count": 0,
                "offset_mm": (-1.6, 9.0, 0.0),
                "body_name": "tab",
            },
        ],
    },
    "nmos-irf540n": {
        "outline": "TO-220",
        "source": "JEDEC TO-220AB (10.04-10.41 mm wide, 2.54 mm pitch)",
        "note": "Tab hole omitted; Z-long orientation with centered leads.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 4.6,
                "body_width_mm": 10.2,
                "body_height_mm": 9.0,
                "pin_count": 3,
                "pin_pitch_mm": 2.54,
                "pin_rows": 3,
                "pin_length_mm": 5.0,
                "body_name": "body",
            },
            {
                "kind": "box",
                "body_length_mm": 1.4,
                "body_width_mm": 10.2,
                "body_height_mm": 6.0,
                "pin_count": 0,
                "offset_mm": (-1.6, 9.0, 0.0),
                "body_name": "tab",
            },
        ],
    },
    "adc-ads1115": {
        "outline": "VSSOP-10",
        "source": "TI VSSOP-10 (3.00 x 3.00 mm, 0.5 mm pitch)",
        "note": "Height nominal MSOP profile.",
        "solids": [
            {
                "kind": "box",
                "body_length_mm": 3.0,
                "body_width_mm": 3.0,
                "body_height_mm": 1.0,
                "pin_count": 10,
                "pin_pitch_mm": 0.5,
                "pin_rows": 2,
                "pin_length_mm": 0.4,
                "body_name": "body",
            },
        ],
    },
}

VISUAL_SPECS: dict[str, tuple[ProceduralSpec, ...]] = {
    component_id: tuple(ProceduralSpec.model_validate(solid) for solid in row["solids"])
    for component_id, row in PART_VISUALS.items()
}


PACK_ID = "electronics"
PACK_VERSION = "1.1.0"
DISPLAY = "Electronics"
THRESHOLD = 2

SIGNALS: tuple[str, ...] = (
    "transistor",
    "circuit",
    "voltage",
    "sram",
    "dram",
    "cmos",
    "mosfet",
    "nmos",
    "pmos",
    "nbti",
    "pbti",
    "leakage",
    "bias",
    "inverter",
    "amplifier",
    "adc",
    "dac",
    "oscillator",
    "silicon",
    "spice",
    "schematic",
    "resistor",
    "capacitor",
    "inductor",
    "diode",
)

ENTITY_TYPES: tuple[EntityTypeDef, ...] = (
    EntityTypeDef(
        "memory-cell",
        "Memory cell",
        "package",
        ("sram", "dram", "memory cell", "bitcell", "6t"),
        (power_iface(), data_iface()),
        symbol="bitcell",
    ),
    EntityTypeDef(
        "transistor",
        "Transistor",
        "discrete",
        ("transistor", "mosfet", "nmos", "pmos", "finfet", "bjt"),
        (power_iface(), InterfaceDef("gate", "signal"), InterfaceDef("channel", "signal")),
        symbol="transistor",
    ),
    EntityTypeDef(
        "logic-gate",
        "Logic gate",
        "package",
        ("inverter", "nand", "nor", "logic gate"),
        (power_iface(), data_iface()),
        symbol="gate",
    ),
    EntityTypeDef(
        "voltage-source",
        "Voltage source",
        "power",
        ("voltage source", "vdd", "supply", "regulator", "reference"),
        (power_iface(),),
        symbol="source",
    ),
    EntityTypeDef(
        "bias-controller",
        "Bias controller",
        "package",
        ("bias", "body bias", "compensation", "back bias"),
        (power_iface(), InterfaceDef("bias", "analog")),
        symbol="bias",
    ),
    EntityTypeDef(
        "sense-amplifier",
        "Sense amplifier",
        "package",
        ("sense", "sensing", "sense amplifier", "readout", "comparator"),
        (power_iface(), data_iface(), InterfaceDef("sense", "analog")),
        symbol="senseamp",
    ),
    EntityTypeDef(
        "measurement",
        "Measurement",
        "sensor",
        ("monitor", "measurement", "meter", "probe", "detector", "current mirror"),
        (power_iface(), InterfaceDef("sense", "analog")),
        symbol="meter",
    ),
    EntityTypeDef(
        "passive",
        "Passive component",
        "passive",
        ("resistor", "capacitor", "inductor", "resistance", "capacitance"),
        (power_iface(),),
        symbol="passive",
    ),
    EntityTypeDef(
        "diode",
        "Diode",
        "discrete",
        ("diode", "rectifier", "schottky", "zener", "1n4148"),
        (
            InterfaceDef("anode", "signal"),
            InterfaceDef("cathode", "signal"),
        ),
        symbol="diode",
    ),
    EntityTypeDef(
        "analog-ic",
        "Analog IC",
        "package",
        ("op-amp", "opamp", "operational amplifier", "timer", "ne555", "lm358"),
        (power_iface(), InterfaceDef("in", "analog"), InterfaceDef("out", "analog")),
        symbol="chip",
    ),
    EntityTypeDef(
        "data-converter",
        "Data converter",
        "package",
        ("adc", "dac", "data converter", "analog-to-digital", "digital-to-analog"),
        (power_iface(), InterfaceDef("analog", "analog"), data_iface()),
        symbol="adc",
    ),
)
