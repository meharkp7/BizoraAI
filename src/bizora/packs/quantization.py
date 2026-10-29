"""Model quantization pack: weight formats, engines, evaluators.

Catalog entries and detection profile moved verbatim from the former
core registry into pack data, wired to the generic pack harness.
"""

from typing import Any

from bizora.core.entity_registry import EntityTypeDef, InterfaceDef
from bizora.packs.lexical import LexicalPack, data_iface, tensor_iface

TENSOR = {"name": "tensor", "kind": "tensor", "params": {}}
DATA = {"name": "data", "kind": "data", "params": {}}
CONFIG_IF = {"name": "config", "kind": "config", "params": {}}

COMPONENTS: list[dict[str, Any]] = [
    {
        "component_id": "format-nf4",
        "domain": "quantization",
        "entity_type": "quant-format",
        "category": "format",
        "kind": "operation",
        "label": "NF4 4-bit quantization format",
        "generic": False,
        "manufacturer": "bitsandbytes",
        "part_number": "NF4",
        "headline": "4-bit NormalFloat format for LLM weights with double quantization",
        "description": (
            "NF4 (NormalFloat 4-bit) represents LLM weights in 4 bits using a "
            "quantile-based codebook, normally with blockwise scaling and optional "
            "double quantization. Introduced for QLoRA fine-tuning."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Bits per weight", "value": "4", "typical": False},
            {"name": "Codebook", "value": "NormalFloat quantiles", "typical": False},
            {"name": "Block size", "value": "64", "typical": True},
            {"name": "Double quantization", "value": "supported", "typical": False},
        ],
        "pinout": [],
        "interfaces": [TENSOR, CONFIG_IF],
        "constraints": {},
        "config_schema": [
            {
                "key": "format",
                "label": "Format",
                "type": "string",
                "default": "NF4",
                "required": True,
                "description": "Recorded weight format identity.",
            },
            {
                "key": "blocksize",
                "label": "Block size",
                "type": "number",
                "default": 64,
                "required": True,
                "description": "Blockwise quantization block size.",
            },
            {
                "key": "double_quant",
                "label": "Double quantization",
                "type": "boolean",
                "default": True,
                "required": False,
                "description": "Quantize the quantization constants.",
            },
        ],
        "default_config": {"format": "NF4", "bits": 4, "blocksize": 64, "double_quant": True},
        "evidence": [
            {
                "source": "Dettmers et al., QLoRA (2023)",
                "note": "NF4 definition; reference URL not verified from this environment.",
            },
        ],
    },
    {
        "component_id": "format-fp16",
        "domain": "quantization",
        "entity_type": "quant-format",
        "category": "format",
        "kind": "operation",
        "label": "FP16 half-precision format",
        "generic": False,
        "manufacturer": "IEEE 754",
        "part_number": "binary16",
        "headline": "16-bit IEEE floating point, 1-5-10 bit layout",
        "description": (
            "FP16 (IEEE 754 binary16) half-precision floating point: 1 sign bit, "
            "5 exponent bits, 10 mantissa bits. The standard training and inference "
            "baseline that quantized formats compare against."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Bits per weight", "value": "16", "typical": False},
            {"name": "Layout", "value": "1-5-10 sign-exponent-mantissa", "typical": False},
            {"name": "Max normal", "value": "65504", "typical": False},
        ],
        "pinout": [],
        "interfaces": [TENSOR, CONFIG_IF],
        "constraints": {},
        "config_schema": [
            {
                "key": "format",
                "label": "Format",
                "type": "string",
                "default": "FP16",
                "required": True,
                "description": "Recorded weight format identity.",
            },
        ],
        "default_config": {"format": "FP16", "bits": 16},
        "evidence": [
            {"source": "IEEE 754-2019 binary16", "note": "Format definition."},
        ],
    },
    {
        "component_id": "format-fp32",
        "domain": "quantization",
        "entity_type": "quant-format",
        "category": "format",
        "kind": "operation",
        "label": "FP32 single-precision format",
        "generic": False,
        "manufacturer": "IEEE 754",
        "part_number": "binary32",
        "headline": "32-bit IEEE floating point reference precision",
        "description": (
            "FP32 (IEEE 754 binary32) single-precision floating point. The "
            "full-precision reference for measuring quantization error."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Bits per weight", "value": "32", "typical": False},
            {"name": "Layout", "value": "1-8-23 sign-exponent-mantissa", "typical": False},
        ],
        "pinout": [],
        "interfaces": [TENSOR, CONFIG_IF],
        "constraints": {},
        "config_schema": [
            {
                "key": "format",
                "label": "Format",
                "type": "string",
                "default": "FP32",
                "required": True,
                "description": "Recorded weight format identity.",
            },
        ],
        "default_config": {"format": "FP32", "bits": 32},
        "evidence": [{"source": "IEEE 754-2019 binary32", "note": "Format definition."}],
    },
    {
        "component_id": "format-int8",
        "domain": "quantization",
        "entity_type": "quant-format",
        "category": "format",
        "kind": "operation",
        "label": "INT8 8-bit integer format",
        "generic": False,
        "manufacturer": "open standard",
        "part_number": "INT8",
        "headline": "8-bit integer weights with per-channel or per-tensor scales",
        "description": (
            "INT8 8-bit integer quantization with floating-point scales, the common "
            "accuracy-preserving step between FP16 and 4-bit formats."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Bits per weight", "value": "8", "typical": False},
            {"name": "Range", "value": "-128 to 127", "typical": False},
        ],
        "pinout": [],
        "interfaces": [TENSOR, CONFIG_IF],
        "constraints": {},
        "config_schema": [
            {
                "key": "format",
                "label": "Format",
                "type": "string",
                "default": "INT8",
                "required": True,
                "description": "Recorded weight format identity.",
            },
            {
                "key": "scale_granularity",
                "label": "Scale granularity",
                "type": "enum",
                "default": "per-channel",
                "options": ["per-tensor", "per-channel", "per-group"],
                "required": True,
                "description": "Granularity of the quantization scales.",
            },
        ],
        "default_config": {"format": "INT8", "bits": 8, "scale_granularity": "per-channel"},
        "evidence": [],
    },
    {
        "component_id": "format-gptq",
        "domain": "quantization",
        "entity_type": "quant-format",
        "category": "format",
        "kind": "operation",
        "label": "GPTQ quantized weights",
        "generic": False,
        "manufacturer": "open method",
        "part_number": "GPTQ",
        "headline": "Layer-wise 4-bit quantization via approximate second-order information",
        "description": (
            "GPTQ compresses weights to 4 (or 3/8) bits layer by layer using Hessian "
            "information, normally with group-wise scaling."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Bits per weight", "value": "4", "typical": True},
            {"name": "Group size", "value": "128", "typical": True},
        ],
        "pinout": [],
        "interfaces": [TENSOR, CONFIG_IF],
        "constraints": {},
        "config_schema": [
            {
                "key": "format",
                "label": "Format",
                "type": "string",
                "default": "GPTQ",
                "required": True,
                "description": "Recorded weight format identity.",
            },
            {
                "key": "bits",
                "label": "Bits",
                "type": "enum",
                "default": "4",
                "options": ["3", "4", "8"],
                "required": True,
                "description": "Target bit-width.",
            },
            {
                "key": "groupsize",
                "label": "Group size",
                "type": "number",
                "default": 128,
                "required": False,
                "description": "Group size for group-wise scaling.",
            },
        ],
        "default_config": {"format": "GPTQ", "bits": 4, "groupsize": 128},
        "evidence": [
            {
                "source": "Frantar et al., GPTQ (2022)",
                "note": "Method definition; reference URL not verified from this environment.",
            },
        ],
    },
    {
        "component_id": "format-awq",
        "domain": "quantization",
        "entity_type": "quant-format",
        "category": "format",
        "kind": "operation",
        "label": "AWQ quantized weights",
        "generic": False,
        "manufacturer": "open method",
        "part_number": "AWQ",
        "headline": "Activation-aware 4-bit weight quantization",
        "description": (
            "AWQ (Activation-aware Weight Quantization) protects salient weight "
            "channels identified from activation statistics before quantizing."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [
            {"name": "Bits per weight", "value": "4", "typical": True},
            {"name": "Salient protection", "value": "activation-aware scaling", "typical": False},
        ],
        "pinout": [],
        "interfaces": [TENSOR, CONFIG_IF],
        "constraints": {},
        "config_schema": [
            {
                "key": "format",
                "label": "Format",
                "type": "string",
                "default": "AWQ",
                "required": True,
                "description": "Recorded weight format identity.",
            },
            {
                "key": "bits",
                "label": "Bits",
                "type": "enum",
                "default": "4",
                "options": ["4"],
                "required": True,
                "description": "Target bit-width.",
            },
        ],
        "default_config": {"format": "AWQ", "bits": 4},
        "evidence": [
            {
                "source": "Lin et al., AWQ (2023)",
                "note": "Method definition; reference URL not verified from this environment.",
            },
        ],
    },
    {
        "component_id": "weights-llm-generic",
        "domain": "quantization",
        "entity_type": "weight-tensor",
        "category": "format",
        "kind": "input",
        "label": "LLM weight checkpoint (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic pretrained weight tensor entering quantization",
        "description": (
            "Generic LLM weight checkpoint consumed by a quantization format stage. "
            "No exact model or checkpoint is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [TENSOR],
        "constraints": {},
        "config_schema": [
            {
                "key": "parameters_b",
                "label": "Parameters (billions)",
                "type": "number",
                "default": 7,
                "required": False,
                "description": "Approximate model size for memory estimates.",
            },
        ],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "engine-inference-generic",
        "domain": "quantization",
        "entity_type": "inference-engine",
        "category": "compute",
        "kind": "model",
        "label": "LLM inference engine (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic quantized-weight inference runtime",
        "description": (
            "Generic inference runtime executing the quantized weights. "
            "No exact engine (vLLM, llama.cpp, ...) is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [TENSOR, {"name": "api", "kind": "protocol", "params": {}}],
        "constraints": {},
        "config_schema": [
            {
                "key": "max_tokens",
                "label": "Max tokens",
                "type": "number",
                "default": 512,
                "required": False,
                "description": "Maximum generation length for evaluation.",
            },
        ],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "eval-perplexity-generic",
        "domain": "quantization",
        "entity_type": "quant-evaluator",
        "category": "compute",
        "kind": "evaluation",
        "label": "Perplexity evaluator (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic perplexity benchmark over the quantized model",
        "description": (
            "Generic evaluator measuring perplexity (or accuracy) degradation from "
            "quantization. No exact dataset or harness is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [DATA],
        "constraints": {},
        "config_schema": [
            {
                "key": "metric",
                "label": "Metric",
                "type": "enum",
                "default": "perplexity",
                "options": ["perplexity", "accuracy"],
                "required": True,
                "description": "Evaluation metric recorded on the node.",
            },
        ],
        "default_config": {"metric": "perplexity"},
        "evidence": [],
    },
]


PACK_ID = "quantization"
PACK_VERSION = "1.0.0"
DISPLAY = "Model quantization"
THRESHOLD = 2

SIGNALS: tuple[str, ...] = (
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
)

ENTITY_TYPES: tuple[EntityTypeDef, ...] = (
    EntityTypeDef(
        "weight-tensor",
        "Weight tensor",
        "format",
        ("weight", "weights", "parameter", "tensor", "checkpoint"),
        (tensor_iface(),),
        physical=False,
        symbol="tensor",
    ),
    EntityTypeDef(
        "quant-format",
        "Quantization format",
        "format",
        ("nf4", "fp16", "fp32", "int8", "int4", "format", "dtype", "quant"),
        (tensor_iface(), InterfaceDef("config", "config")),
        identity_keys=("format", "dtype", "bits"),
        physical=False,
        symbol="format",
    ),
    EntityTypeDef(
        "inference-engine",
        "Inference engine",
        "compute",
        ("inference", "inference engine", "runtime", "server", "vllm", "llama.cpp"),
        (tensor_iface(), InterfaceDef("api", "protocol")),
        physical=False,
        symbol="engine",
    ),
    EntityTypeDef(
        "quant-evaluator",
        "Quantization evaluator",
        "compute",
        ("evaluat", "perplexity", "benchmark", "accuracy", "error metric"),
        (data_iface(),),
        physical=False,
        symbol="evaluator",
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
