"""Extensible domain and entity registry.

Profiles describe research domains in generic vocabulary: weighted
detection signals plus the entity types each domain understands. Adding a
domain means appending one profile; renderers and validators consume the
registry without per-paper branches.

Matching is deliberately lexical and explainable: every resolution records
the terms that grounded it, and anything unmatched resolves to an explicit
generic fallback instead of a fabricated part.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bizora.contracts.domain import (
    GENERIC_DOMAIN,
    DomainClassification,
    EntityResolution,
    InterfaceSpec,
    MissingInterface,
    ReplacementCompatibility,
)


@dataclass(frozen=True)
class InterfaceDef:
    """An interface kind an entity type exposes."""

    name: str
    kind: str
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EntityTypeDef:
    """One resolvable entity type within a domain."""

    type_id: str
    display: str
    category: str
    match_terms: tuple[str, ...]
    interfaces: tuple[InterfaceDef, ...] = ()
    # Config keys whose values pin an exact identity (model numbers, ...).
    identity_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainProfile:
    """Detection signals and entity types for one research domain."""

    domain: str
    display: str
    signals: tuple[str, ...]
    entity_types: tuple[EntityTypeDef, ...] = ()
    fallback_category: str = "generic"
    # Minimum distinct signals before the domain wins over generic.
    threshold: int = 2


def _power(voltage_key: str | None = None) -> InterfaceDef:
    params = {"voltage": voltage_key} if voltage_key else {}
    return InterfaceDef(name="power", kind="power", params=params)


def _data() -> InterfaceDef:
    return InterfaceDef(name="data", kind="data")


def _tensor() -> InterfaceDef:
    return InterfaceDef(name="tensor", kind="tensor")


PROFILES: dict[str, DomainProfile] = {
    "electronics": DomainProfile(
        domain="electronics",
        display="Electronics",
        signals=(
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
        ),
        entity_types=(
            EntityTypeDef(
                "memory-cell",
                "Memory cell",
                "package",
                ("sram", "dram", "memory cell", "bitcell", "6t"),
                (_power(), _data()),
            ),
            EntityTypeDef(
                "transistor",
                "Transistor",
                "discrete",
                ("transistor", "mosfet", "nmos", "pmos", "finfet", "bjt"),
                (_power(), InterfaceDef("gate", "signal"), InterfaceDef("channel", "signal")),
            ),
            EntityTypeDef(
                "logic-gate",
                "Logic gate",
                "package",
                ("inverter", "nand", "nor", "logic gate"),
                (_power(), _data()),
            ),
            EntityTypeDef(
                "voltage-source",
                "Voltage source",
                "power",
                ("voltage source", "vdd", "supply", "regulator", "reference"),
                (_power(),),
            ),
            EntityTypeDef(
                "bias-controller",
                "Bias controller",
                "package",
                ("bias", "body bias", "compensation", "back bias"),
                (_power(), InterfaceDef("bias", "analog")),
            ),
            EntityTypeDef(
                "sense-amplifier",
                "Sense amplifier",
                "package",
                ("sense", "sensing", "sense amplifier", "readout", "comparator"),
                (_power(), _data(), InterfaceDef("sense", "analog")),
            ),
            EntityTypeDef(
                "measurement",
                "Measurement",
                "sensor",
                ("monitor", "measurement", "meter", "probe", "detector", "current mirror"),
                (_power(), InterfaceDef("sense", "analog")),
            ),
            EntityTypeDef(
                "passive",
                "Passive component",
                "passive",
                ("resistor", "capacitor", "inductor", "resistance", "capacitance"),
                (_power(),),
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
            ),
            EntityTypeDef(
                "analog-ic",
                "Analog IC",
                "package",
                ("op-amp", "opamp", "operational amplifier", "timer", "ne555", "lm358"),
                (_power(), InterfaceDef("in", "analog"), InterfaceDef("out", "analog")),
            ),
            EntityTypeDef(
                "data-converter",
                "Data converter",
                "package",
                ("adc", "dac", "data converter", "analog-to-digital", "digital-to-analog"),
                (_power(), InterfaceDef("analog", "analog"), _data()),
            ),
        ),
    ),
    "iot": DomainProfile(
        domain="iot",
        display="IoT systems",
        signals=(
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
        ),
        entity_types=(
            EntityTypeDef(
                "microcontroller",
                "Microcontroller",
                "compute",
                ("microcontroller", "mcu", "esp32", "arduino", "raspberry", "stm32"),
                (_power(), InterfaceDef("gpio", "gpio"), _data()),
                identity_keys=("model", "part"),
            ),
            EntityTypeDef(
                "sensor-module",
                "Sensor module",
                "sensor",
                ("sensor", "temperature", "humidity", "pressure", "accelerometer", "dht", "bme"),
                (_power(), _data()),
                identity_keys=("model", "part"),
            ),
            EntityTypeDef(
                "actuator",
                "Actuator",
                "compute",
                ("actuator", "relay", "motor", "servo", "valve"),
                (_power(), InterfaceDef("control", "signal")),
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
                (_power(), InterfaceDef("air", "rf"), _data()),
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
                (_power(),),
            ),
        ),
    ),
    "quantization": DomainProfile(
        domain="quantization",
        display="Model quantization",
        signals=(
            "quantization",
            "quantize",
            "quantized",
            "nf4",
            "fp16",
            "fp32",
            "int8",
            "int4",
            "bitsandbytes",
            "gguf",
            "awq",
            "gptq",
            "dequant",
            "precision",
            "bit-width",
            "bitwidth",
        ),
        entity_types=(
            EntityTypeDef(
                "weight-tensor",
                "Weight tensor",
                "format",
                ("weight", "weights", "parameter", "tensor", "checkpoint"),
                (_tensor(),),
            ),
            EntityTypeDef(
                "quant-format",
                "Quantization format",
                "format",
                ("nf4", "fp16", "fp32", "int8", "int4", "format", "dtype", "quant"),
                (_tensor(), InterfaceDef("config", "config")),
                identity_keys=("format", "dtype", "bits"),
            ),
            EntityTypeDef(
                "inference-engine",
                "Inference engine",
                "compute",
                ("inference", "inference engine", "runtime", "server", "vllm", "llama.cpp"),
                (_tensor(), InterfaceDef("api", "protocol")),
            ),
            EntityTypeDef(
                "quant-evaluator",
                "Quantization evaluator",
                "compute",
                ("evaluat", "perplexity", "benchmark", "accuracy", "error metric"),
                (_data(),),
            ),
        ),
    ),
    "signal-processing": DomainProfile(
        domain="signal-processing",
        display="Signal processing",
        signals=(
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
        ),
        entity_types=(
            EntityTypeDef(
                "sampler",
                "Sampler",
                "signal",
                ("sampl", "adc", "digitiz", "microphone"),
                (InterfaceDef("analog-in", "analog"), InterfaceDef("samples", "signal")),
            ),
            EntityTypeDef(
                "source-encoder",
                "Source encoder",
                "signal",
                ("encod", "codec", "compress"),
                (InterfaceDef("bits", "data"),),
            ),
            EntityTypeDef(
                "modulator",
                "Modulator",
                "signal",
                ("modulat", "qam", "psk", "fsk", "ofdm", "mapper"),
                (InterfaceDef("symbols", "signal"), InterfaceDef("carrier", "analog")),
            ),
            EntityTypeDef(
                "channel-model",
                "Channel",
                "network",
                ("channel", "awgn", "fading", "transmission", "medium"),
                (InterfaceDef("in", "signal"), InterfaceDef("out", "signal")),
            ),
            EntityTypeDef(
                "demodulator",
                "Demodulator",
                "signal",
                ("demodulat", "demapper", "detector", "equaliz"),
                (InterfaceDef("symbols", "signal"), InterfaceDef("bits", "data")),
            ),
            EntityTypeDef(
                "source-decoder",
                "Source decoder",
                "signal",
                ("decod", "reconstruct", "synthes", "playback", "speaker"),
                (InterfaceDef("samples", "signal"),),
            ),
            EntityTypeDef(
                "filter",
                "Filter",
                "signal",
                ("filter", "equalizer", "mixer", "amplifier"),
                (InterfaceDef("in", "signal"), InterfaceDef("out", "signal")),
            ),
        ),
    ),
    "distributed-systems": DomainProfile(
        domain="distributed-systems",
        display="Distributed systems",
        signals=(
            "replica",
            "replication",
            "coordinator",
            "worker",
            "client",
            "consensus",
            "raft",
            "paxos",
            "shard",
            "partition",
            "fault",
            "leader",
            "follower",
            "quorum",
            "throughput",
            "latency",
            "cluster",
            "scheduler",
            "database",
            "storage engine",
            "transaction",
        ),
        entity_types=(
            EntityTypeDef(
                "client",
                "Client",
                "service",
                ("client", "frontend", "cli", "sdk"),
                (InterfaceDef("requests", "protocol"),),
            ),
            EntityTypeDef(
                "coordinator",
                "Coordinator",
                "service",
                ("coordinator", "leader", "master", "scheduler", "controller", "gateway"),
                (InterfaceDef("control", "protocol"), _data()),
            ),
            EntityTypeDef(
                "worker",
                "Worker",
                "service",
                ("worker", "executor", "task", "follower", "agent"),
                (InterfaceDef("control", "protocol"), _data()),
            ),
            EntityTypeDef(
                "storage-node",
                "Storage node",
                "storage",
                ("storage", "database", "shard", "disk", "sst", "wal", "log", "cache"),
                (InterfaceDef("store", "storage"), InterfaceDef("replication", "replication")),
            ),
            EntityTypeDef(
                "message-queue",
                "Message queue",
                "network",
                ("queue", "broker", "kafka", "stream", "pubsub", "topic"),
                (InterfaceDef("publish", "protocol"), InterfaceDef("subscribe", "protocol")),
            ),
            EntityTypeDef(
                "load-balancer",
                "Load balancer",
                "network",
                ("load balanc", "proxy", "router", "ingress"),
                (InterfaceDef("frontend", "protocol"), InterfaceDef("backend", "protocol")),
            ),
        ),
    ),
    "deep-learning": DomainProfile(
        domain="deep-learning",
        display="Deep learning",
        signals=(
            "transformer",
            "attention",
            "embedding",
            "encoder",
            "decoder",
            "layer",
            "training",
            "gradient",
            "backprop",
            "epoch",
            "batch",
            "optimizer",
            "adam",
            "loss",
            "checkpoint",
            "fine-tun",
            "pretrain",
            "token",
            "feed-forward",
            "normalization",
        ),
        entity_types=(
            EntityTypeDef(
                "embedding",
                "Embedding",
                "layer",
                ("embed", "tokeniz", "positional"),
                (_tensor(),),
            ),
            EntityTypeDef(
                "attention-block",
                "Attention block",
                "layer",
                ("attention", "self-attention", "multi-head", "mha"),
                (_tensor(),),
            ),
            EntityTypeDef(
                "feedforward-block",
                "Feed-forward block",
                "layer",
                ("feed-forward", "ffn", "mlp", "linear", "dense"),
                (_tensor(),),
            ),
            EntityTypeDef(
                "normalization",
                "Normalization",
                "layer",
                ("normaliz", "layernorm", "rmsnorm", "batchnorm"),
                (_tensor(),),
            ),
            EntityTypeDef(
                "loss-function",
                "Loss function",
                "compute",
                ("loss", "objective", "cross-entropy", "mse"),
                (_tensor(), InterfaceDef("gradients", "tensor")),
            ),
            EntityTypeDef(
                "optimizer",
                "Optimizer",
                "compute",
                ("optimiz", "adam", "sgd", "scheduler", "learning rate"),
                (InterfaceDef("gradients", "tensor"), InterfaceDef("state", "storage")),
            ),
            EntityTypeDef(
                "dataloader",
                "Data loader",
                "storage",
                ("dataset", "dataloader", "corpus", "shard", "batch", "training"),
                (_tensor(),),
            ),
            EntityTypeDef(
                "model-evaluator",
                "Model evaluator",
                "compute",
                ("evaluat", "benchmark", "metric", "validation", "test set"),
                (_data(),),
            ),
        ),
    ),
}


def _terms_matched(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    lowered = text.lower()
    return tuple(term for term in terms if term in lowered)


def _dedup_overlapping(matched: tuple[str, ...]) -> tuple[str, ...]:
    """Drop a term contained in another matched term.

    Without this, "cli" counts separately inside "client" and inflates
    the wrong candidate.
    """
    return tuple(
        term for term in matched if not any(other != term and term in other for other in matched)
    )


def _match_score(
    label_matched: tuple[str, ...], total_matched: tuple[str, ...]
) -> tuple[int, int, int, int]:
    """Rank candidates: label hits first, then longer (more specific) terms.

    The label names the node, so its matches outweigh description words
    ("coordinator ... client requests" is a coordinator, not a client).
    Longer terms win ties ("demodulat" beats "modulat" for Demodulator).
    """
    return (
        len(label_matched),
        max((len(term) for term in label_matched), default=0),
        len(total_matched),
        max((len(term) for term in total_matched), default=0),
    )


def _node_text(label: str, description: str | None, kind: str, config: object) -> str:
    parts = [label, kind]
    if description:
        parts.append(description)
    parts.append(repr(config))
    return " ".join(parts)


def detect_domain(
    title: str,
    brief_text: str,
    nodes: tuple[tuple[str, str | None, str, object], ...],
) -> DomainClassification:
    """Score registry signals over graph text; fall back to generic."""
    haystack = " ".join(
        [title, brief_text]
        + [
            _node_text(label, description, kind, config)
            for label, description, kind, config in nodes
        ]
    )
    best_domain = GENERIC_DOMAIN
    best_signals: tuple[str, ...] = ()
    for profile in PROFILES.values():
        matched = _terms_matched(haystack, profile.signals)
        if len(matched) >= profile.threshold and len(matched) > len(best_signals):
            best_domain = profile.domain
            best_signals = matched
    confidence = len(best_signals) / (len(best_signals) + 2) if best_signals else 0.0
    return DomainClassification(
        domain=best_domain, confidence=round(confidence, 3), signals=best_signals
    )


def _exact_identity(node_config: object, identity_keys: tuple[str, ...]) -> str | None:
    if not isinstance(node_config, dict) or not identity_keys:
        return None
    for key in identity_keys:
        value = node_config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return None


def resolve_node(
    profile: DomainProfile,
    node_id: str,
    label: str,
    description: str | None,
    kind: str,
    config: object,
) -> EntityResolution:
    """Resolve one node to the best entity type, or a generic fallback."""
    text = _node_text(label, description, kind, config)
    best: EntityTypeDef | None = None
    best_terms: tuple[str, ...] = ()
    best_score: tuple[int, int, int, int] = (-1, -1, -1, -1)
    for candidate in profile.entity_types:
        label_matched = _dedup_overlapping(_terms_matched(label.lower(), candidate.match_terms))
        total_matched = _dedup_overlapping(_terms_matched(text, candidate.match_terms))
        if not total_matched:
            continue
        score = _match_score(label_matched, total_matched)
        if score > best_score:
            best = candidate
            best_terms = total_matched
            best_score = score
    if best is None:
        return EntityResolution(
            node_id=node_id,
            domain=profile.domain,
            entity_type="generic-component",
            display_label=label,
            generic=True,
            category=profile.fallback_category,
            interfaces=(),
            matched_terms=(),
            confidence=0.0,
        )
    identity = _exact_identity(config, best.identity_keys)
    interfaces = tuple(
        InterfaceSpec(name=iface.name, kind=iface.kind, params=dict(iface.params))
        for iface in best.interfaces
    )
    confidence = min(0.5 + 0.25 * len(best_terms) + (0.25 if identity else 0.0), 1.0)
    # A matched type is an exact entity type even when the paper gives no
    # model number; only the unmatched fallback is a generic placeholder.
    return EntityResolution(
        node_id=node_id,
        domain=profile.domain,
        entity_type=best.type_id,
        display_label=identity or best.display,
        generic=False,
        category=best.category,
        interfaces=interfaces,
        matched_terms=best_terms,
        confidence=round(confidence, 3),
    )


def resolve_generic(node_id: str, label: str) -> EntityResolution:
    """Resolve a node when no domain matched: an honest unknown."""
    return EntityResolution(
        node_id=node_id,
        domain=GENERIC_DOMAIN,
        entity_type="generic-component",
        display_label=label,
        generic=True,
        category="generic",
        interfaces=(),
        matched_terms=(),
        confidence=0.0,
    )


def check_compatible(
    old: EntityResolution,
    new: EntityResolution,
    incident_edge_ids: tuple[str, ...],
) -> ReplacementCompatibility:
    """Report whether a replacement keeps its predecessor's interfaces.

    Unknown (generic) interfaces never conflict: only known kinds the
    replacement drops block the swap. Shared parameter keys must agree.
    """
    if old.generic or new.generic or not old.interfaces:
        return ReplacementCompatibility(compatible=True, incident_edge_ids=incident_edge_ids)
    new_by_kind = {iface.kind: iface for iface in new.interfaces}
    missing: list[MissingInterface] = []
    for iface in old.interfaces:
        replacement = new_by_kind.get(iface.kind)
        if replacement is None:
            missing.append(
                MissingInterface(
                    kind=iface.kind,
                    reason=f"Replacement {new.entity_type!r} exposes no {iface.kind!r} interface.",
                )
            )
            continue
        for key, value in iface.params.items():
            if key in replacement.params and replacement.params[key] != value:
                missing.append(
                    MissingInterface(
                        kind=iface.kind,
                        reason=(
                            f"Interface {iface.kind!r} parameter {key!r} changes "
                            f"from {value!r} to {replacement.params[key]!r}."
                        ),
                    )
                )
    return ReplacementCompatibility(
        compatible=not missing,
        missing_interfaces=tuple(missing),
        incident_edge_ids=incident_edge_ids,
    )
