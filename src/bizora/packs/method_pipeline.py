"""Method-pipeline pack: generic research-pipeline stages.

Dataset, split, preprocessing, augmentation, baseline model, and evaluator
as correctly identified generics: no exact parts, no claimed numbers. This
pack routes method-flow graphs that no specialized domain claims; it
registers last so affinity ties always resolve to a specialized pack.
"""

from typing import Any

from bizora.core.entity_registry import EntityTypeDef
from bizora.packs.lexical import LexicalPack, data_iface, tensor_iface

DATA = {"name": "data", "kind": "data", "params": {}}
TENSOR = {"name": "tensor", "kind": "tensor", "params": {}}
CONFIG_IF = {"name": "config", "kind": "config", "params": {}}

COMPONENTS: list[dict[str, Any]] = [
    {
        "component_id": "dataset-generic",
        "domain": "method-pipeline",
        "entity_type": "pipeline-dataset",
        "category": "storage",
        "kind": "dataset",
        "label": "Dataset (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic research dataset with a recorded split",
        "description": (
            "Generic dataset placeholder: records which split of which named "
            "dataset feeds the pipeline. No size, license, or content is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [DATA],
        "constraints": {},
        "config_schema": [
            {
                "key": "name",
                "label": "Dataset name",
                "type": "string",
                "default": "",
                "required": True,
                "description": "Dataset name as stated by the paper.",
            },
            {
                "key": "split",
                "label": "Split",
                "type": "enum",
                "default": "train",
                "options": ["train", "validation", "test"],
                "required": True,
                "description": "Which split this node carries.",
            },
        ],
        "default_config": {"name": "", "split": "train"},
        "evidence": [],
    },
    {
        "component_id": "split-generic",
        "domain": "method-pipeline",
        "entity_type": "pipeline-stage",
        "category": "process",
        "kind": "preprocessing",
        "label": "Train/val/test split (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic dataset split with recorded ratios",
        "description": (
            "Generic split stage: records train, validation, and test ratios. "
            "No sampling strategy or seed handling is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [DATA],
        "constraints": {},
        "config_schema": [
            {
                "key": "train",
                "label": "Train ratio",
                "type": "number",
                "default": 0.8,
                "required": True,
                "description": "Training share of the data.",
            },
            {
                "key": "validation",
                "label": "Validation ratio",
                "type": "number",
                "default": 0.1,
                "required": True,
                "description": "Validation share of the data.",
            },
            {
                "key": "test",
                "label": "Test ratio",
                "type": "number",
                "default": 0.1,
                "required": True,
                "description": "Test share of the data.",
            },
        ],
        "default_config": {"train": 0.8, "validation": 0.1, "test": 0.1},
        "evidence": [],
    },
    {
        "component_id": "preprocess-generic",
        "domain": "method-pipeline",
        "entity_type": "pipeline-stage",
        "category": "process",
        "kind": "preprocessing",
        "label": "Preprocessing stage (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic preprocessing step with named operations",
        "description": (
            "Generic preprocessing stage: names the operations applied before "
            "modeling. No operation semantics are implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [DATA, CONFIG_IF],
        "constraints": {},
        "config_schema": [
            {
                "key": "operations",
                "label": "Operations",
                "type": "string",
                "default": "",
                "required": True,
                "description": "Comma-separated operation names from the paper.",
            },
        ],
        "default_config": {"operations": ""},
        "evidence": [],
    },
    {
        "component_id": "augment-generic",
        "domain": "method-pipeline",
        "entity_type": "pipeline-stage",
        "category": "process",
        "kind": "preprocessing",
        "label": "Augmentation stage (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic data augmentation with a recorded policy",
        "description": (
            "Generic augmentation stage: records the augmentation policy name. "
            "No transform parameters are implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [DATA, CONFIG_IF],
        "constraints": {},
        "config_schema": [
            {
                "key": "policy",
                "label": "Policy",
                "type": "string",
                "default": "",
                "required": True,
                "description": "Augmentation policy name from the paper.",
            },
        ],
        "default_config": {"policy": ""},
        "evidence": [],
    },
    {
        "component_id": "baseline-model-generic",
        "domain": "method-pipeline",
        "entity_type": "pipeline-model",
        "category": "compute",
        "kind": "model",
        "label": "Baseline model (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic baseline model with a recorded family",
        "description": (
            "Generic baseline model: records the model family name for "
            "comparison. No architecture or size is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [TENSOR, CONFIG_IF],
        "constraints": {},
        "config_schema": [
            {
                "key": "family",
                "label": "Model family",
                "type": "string",
                "default": "",
                "required": True,
                "description": "Model family name from the paper.",
            },
        ],
        "default_config": {"family": ""},
        "evidence": [],
    },
    {
        "component_id": "evaluator-generic",
        "domain": "method-pipeline",
        "entity_type": "pipeline-evaluator",
        "category": "compute",
        "kind": "evaluation",
        "label": "Evaluator (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic evaluator with a recorded metric",
        "description": (
            "Generic evaluator: records the metric computed over a split. "
            "No metric value is implied."
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
                "type": "string",
                "default": "",
                "required": True,
                "description": "Metric name from the paper.",
            },
            {
                "key": "split",
                "label": "Split",
                "type": "enum",
                "default": "test",
                "options": ["train", "validation", "test"],
                "required": True,
                "description": "Which split the metric covers.",
            },
        ],
        "default_config": {"metric": "", "split": "test"},
        "evidence": [],
    },
]


PACK_ID = "method-pipeline"
PACK_VERSION = "1.0.0"
DISPLAY = "Method pipeline"
THRESHOLD = 2

SIGNALS: tuple[str, ...] = (
    "dataset",
    "preprocessing",
    "preprocess",
    "augmentation",
    "augment",
    "split",
    "training",
    "validation",
    "evaluation",
    "baseline",
    "ablation",
    "benchmark",
    "checkpoint",
    "epoch",
    "batch",
    "pipeline",
)

ENTITY_TYPES: tuple[EntityTypeDef, ...] = (
    EntityTypeDef(
        "pipeline-dataset",
        "Pipeline dataset",
        "storage",
        ("dataset", "corpus", "samples", "images", "records"),
        (data_iface(),),
        physical=False,
        symbol="dataset",
    ),
    EntityTypeDef(
        "pipeline-stage",
        "Pipeline stage",
        "process",
        ("preprocess", "preprocessing", "augment", "augmentation", "transform", "split"),
        (data_iface(),),
        physical=False,
        symbol="preprocessing",
    ),
    EntityTypeDef(
        "pipeline-model",
        "Pipeline model",
        "compute",
        ("model", "baseline", "backbone", "classifier", "network"),
        (tensor_iface(),),
        physical=False,
        symbol="operation",
    ),
    EntityTypeDef(
        "pipeline-evaluator",
        "Pipeline evaluator",
        "compute",
        ("evaluat", "benchmark", "metric", "score", "accuracy", "ablation"),
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
