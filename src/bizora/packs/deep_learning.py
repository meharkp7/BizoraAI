"""Deep learning pack: layers, optimizers, data loading, evaluation.

Detection profile moved verbatim from the former core registry into
pack data, wired to the generic pack harness. The pack ships no catalog
entries yet; the real ML/DL pack (Phase 6) supersedes this lexical data.
"""

from typing import Any

from bizora.core.entity_registry import EntityTypeDef, InterfaceDef
from bizora.packs.lexical import LexicalPack, data_iface, tensor_iface

PACK_ID = "deep-learning"
PACK_VERSION = "1.0.0"
DISPLAY = "Deep learning"
THRESHOLD = 2

COMPONENTS: list[dict[str, Any]] = []

SIGNALS: tuple[str, ...] = (
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
)

ENTITY_TYPES: tuple[EntityTypeDef, ...] = (
    EntityTypeDef(
        "embedding",
        "Embedding",
        "layer",
        ("embed", "tokeniz", "positional"),
        (tensor_iface(),),
    ),
    EntityTypeDef(
        "attention-block",
        "Attention block",
        "layer",
        ("attention", "self-attention", "multi-head", "mha"),
        (tensor_iface(),),
    ),
    EntityTypeDef(
        "feedforward-block",
        "Feed-forward block",
        "layer",
        ("feed-forward", "ffn", "mlp", "linear", "dense"),
        (tensor_iface(),),
    ),
    EntityTypeDef(
        "normalization",
        "Normalization",
        "layer",
        ("normaliz", "layernorm", "rmsnorm", "batchnorm"),
        (tensor_iface(),),
    ),
    EntityTypeDef(
        "loss-function",
        "Loss function",
        "compute",
        ("loss", "objective", "cross-entropy", "mse"),
        (tensor_iface(), InterfaceDef("gradients", "tensor")),
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
        (tensor_iface(),),
    ),
    EntityTypeDef(
        "model-evaluator",
        "Model evaluator",
        "compute",
        ("evaluat", "benchmark", "metric", "validation", "test set"),
        (data_iface(),),
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
