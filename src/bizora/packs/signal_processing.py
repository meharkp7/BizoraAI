"""Signal processing pack: generic pipeline stages with schemas.

Catalog entries and detection profile moved verbatim from the former
core registry into pack data, wired to the generic pack harness.
"""

from typing import Any

from bizora.core.entity_registry import EntityTypeDef, InterfaceDef
from bizora.packs.lexical import LexicalPack

ANALOG = {"name": "analog", "kind": "analog", "params": {}}
SIG = {"name": "signal", "kind": "signal", "params": {}}
DATA = {"name": "data", "kind": "data", "params": {}}
SYMBOLS = {"name": "symbols", "kind": "signal", "params": {}}
BITS = {"name": "bits", "kind": "data", "params": {}}

COMPONENTS: list[dict[str, Any]] = [
    {
        "component_id": "sig-sampler-generic",
        "domain": "signal-processing",
        "entity_type": "sampler",
        "category": "signal",
        "kind": "preprocessing",
        "label": "Speech sampler (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic analog-to-sample conversion stage",
        "description": (
            "Generic speech sampling stage producing discrete-time samples from an "
            "analog input. Set the sampling rate and resolution."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [
            {"name": "analog-in", "kind": "analog", "params": {}},
            {"name": "samples", "kind": "signal", "params": {}},
        ],
        "constraints": {},
        "config_schema": [
            {
                "key": "sampling_rate_hz",
                "label": "Sampling rate",
                "type": "number",
                "default": 8000,
                "unit": "Hz",
                "required": True,
                "description": "Samples per second produced by this stage.",
            },
            {
                "key": "bits",
                "label": "Resolution",
                "type": "number",
                "default": 16,
                "unit": "bit",
                "required": False,
                "description": "Bits per sample.",
            },
        ],
        "default_config": {"sampling_rate_hz": 8000, "bits": 16},
        "evidence": [],
    },
    {
        "component_id": "sig-encoder-generic",
        "domain": "signal-processing",
        "entity_type": "source-encoder",
        "category": "signal",
        "kind": "operation",
        "label": "Source encoder (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic speech compression encoder",
        "description": (
            "Generic source encoder compressing samples into a bitstream. "
            "No exact codec is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [BITS],
        "constraints": {},
        "config_schema": [
            {
                "key": "bitrate_bps",
                "label": "Bitrate",
                "type": "number",
                "default": 13000,
                "unit": "bps",
                "required": False,
                "description": "Target encoded bitrate.",
            },
        ],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "sig-modulator-qam",
        "domain": "signal-processing",
        "entity_type": "modulator",
        "category": "signal",
        "kind": "operation",
        "label": "QAM modulator (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic quadrature amplitude modulator with settable order",
        "description": (
            "Generic QAM modulator mapping bits to constellation symbols. "
            "Set the modulation order for the link budget under study."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Family", "value": "QAM", "typical": False}],
        "pinout": [],
        "interfaces": [SYMBOLS, {"name": "carrier", "kind": "analog", "params": {}}],
        "constraints": {},
        "config_schema": [
            {
                "key": "modulation_order",
                "label": "Modulation order",
                "type": "enum",
                "default": "16",
                "options": ["4", "16", "64", "256"],
                "required": True,
                "description": "QAM constellation size.",
            },
        ],
        "default_config": {"modulation_order": "16"},
        "evidence": [],
    },
    {
        "component_id": "sig-modulator-psk",
        "domain": "signal-processing",
        "entity_type": "modulator",
        "category": "signal",
        "kind": "operation",
        "label": "PSK modulator (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic phase-shift-keying modulator with settable order",
        "description": (
            "Generic PSK modulator mapping bits to phase symbols. Alternative to "
            "QAM where constant-envelope transmission matters."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Family", "value": "PSK", "typical": False}],
        "pinout": [],
        "interfaces": [SYMBOLS, {"name": "carrier", "kind": "analog", "params": {}}],
        "constraints": {},
        "config_schema": [
            {
                "key": "modulation_order",
                "label": "Modulation order",
                "type": "enum",
                "default": "8",
                "options": ["2", "4", "8"],
                "required": True,
                "description": "PSK constellation size.",
            },
        ],
        "default_config": {"modulation_order": "8"},
        "evidence": [],
    },
    {
        "component_id": "sig-channel-awgn",
        "domain": "signal-processing",
        "entity_type": "channel-model",
        "category": "network",
        "kind": "component",
        "label": "AWGN channel (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic additive white Gaussian noise channel",
        "description": (
            "Generic AWGN channel model adding Gaussian noise at the configured "
            "signal-to-noise ratio."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Model", "value": "AWGN", "typical": False}],
        "pinout": [],
        "interfaces": [
            {"name": "in", "kind": "signal", "params": {}},
            {"name": "out", "kind": "signal", "params": {}},
        ],
        "constraints": {},
        "config_schema": [
            {
                "key": "snr_db",
                "label": "SNR",
                "type": "number",
                "default": 10,
                "unit": "dB",
                "required": True,
                "description": "Signal-to-noise ratio of the channel.",
            },
        ],
        "default_config": {"snr_db": 10},
        "evidence": [],
    },
    {
        "component_id": "sig-demodulator-generic",
        "domain": "signal-processing",
        "entity_type": "demodulator",
        "category": "signal",
        "kind": "operation",
        "label": "Demodulator (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic symbol-to-bit demodulator",
        "description": (
            "Generic demodulator recovering bits from received symbols. Pair with "
            "the matching modulator order."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [SYMBOLS, BITS],
        "constraints": {},
        "config_schema": [
            {
                "key": "modulation_order",
                "label": "Modulation order",
                "type": "enum",
                "default": "16",
                "options": ["2", "4", "8", "16", "64", "256"],
                "required": True,
                "description": "Constellation size expected from the modulator.",
            },
        ],
        "default_config": {"modulation_order": "16"},
        "evidence": [],
    },
    {
        "component_id": "sig-decoder-generic",
        "domain": "signal-processing",
        "entity_type": "source-decoder",
        "category": "signal",
        "kind": "operation",
        "label": "Source decoder (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic bitstream-to-speech decoder",
        "description": (
            "Generic source decoder reconstructing speech samples from the received "
            "bitstream. No exact codec is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [{"name": "samples", "kind": "signal", "params": {}}],
        "constraints": {},
        "config_schema": [],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "sig-filter-fir",
        "domain": "signal-processing",
        "entity_type": "filter",
        "category": "signal",
        "kind": "operation",
        "label": "FIR filter (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic finite-impulse-response filter stage",
        "description": (
            "Generic FIR filter for shaping or equalizing the signal path. "
            "Set the tap count and cutoff."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Structure", "value": "FIR", "typical": False}],
        "pinout": [],
        "interfaces": [
            {"name": "in", "kind": "signal", "params": {}},
            {"name": "out", "kind": "signal", "params": {}},
        ],
        "constraints": {},
        "config_schema": [
            {
                "key": "taps",
                "label": "Tap count",
                "type": "number",
                "default": 32,
                "required": True,
                "description": "Number of filter taps.",
            },
            {
                "key": "cutoff_hz",
                "label": "Cutoff",
                "type": "number",
                "default": 3400,
                "unit": "Hz",
                "required": False,
                "description": "Low-pass cutoff frequency.",
            },
        ],
        "default_config": {"taps": 32},
        "evidence": [],
    },
]


PACK_ID = "signal-processing"
PACK_VERSION = "1.0.0"
DISPLAY = "Signal processing"
THRESHOLD = 2

SIGNALS: tuple[str, ...] = (
    "modulation",
    "demodulation",
    "modulator",
    "demodulator",
    "sampling",
    "carrier",
    "bandwidth",
    "spectrum",
    "fft",
    "filter",
    "channel",
    "awgn",
    "symbol",
    "waveform",
    "codec",
    "encode",
    "decode",
    "qam",
    "psk",
    "fsk",
    "ofdm",
    "speech",
    "audio",
)

ENTITY_TYPES: tuple[EntityTypeDef, ...] = (
    EntityTypeDef(
        "sampler",
        "Sampler",
        "signal",
        ("sampl", "adc", "digitiz", "microphone"),
        (InterfaceDef("analog-in", "analog"), InterfaceDef("samples", "signal")),
        symbol="sampler",
    ),
    EntityTypeDef(
        "source-encoder",
        "Source encoder",
        "signal",
        ("encod", "codec", "compress"),
        (InterfaceDef("bits", "data"),),
        symbol="encoder",
    ),
    EntityTypeDef(
        "modulator",
        "Modulator",
        "signal",
        ("modulat", "qam", "psk", "fsk", "ofdm", "mapper"),
        (InterfaceDef("symbols", "signal"), InterfaceDef("carrier", "analog")),
        symbol="modulator",
    ),
    EntityTypeDef(
        "channel-model",
        "Channel",
        "network",
        ("channel", "awgn", "fading", "transmission", "medium"),
        (InterfaceDef("in", "signal"), InterfaceDef("out", "signal")),
        physical=False,
        symbol="channel",
    ),
    EntityTypeDef(
        "demodulator",
        "Demodulator",
        "signal",
        ("demodulat", "demapper", "detector", "equaliz"),
        (InterfaceDef("symbols", "signal"), InterfaceDef("bits", "data")),
        symbol="demodulator",
    ),
    EntityTypeDef(
        "source-decoder",
        "Source decoder",
        "signal",
        ("decod", "reconstruct", "synthes", "playback", "speaker"),
        (InterfaceDef("samples", "signal"),),
        symbol="decoder",
    ),
    EntityTypeDef(
        "filter",
        "Filter",
        "signal",
        ("filter", "equalizer", "mixer", "amplifier"),
        (InterfaceDef("in", "signal"), InterfaceDef("out", "signal")),
        symbol="filter",
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
