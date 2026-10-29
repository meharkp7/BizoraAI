"""Deep learning pack: allowlisted layers, graph-to-PyTorch compiler, shape preflight.

Phase 6 supersedes the v1 lexical placeholder with the real ML/DL pack:

- an allowlisted layer vocabulary (eleven structural layer kinds);
- a graph-to-PyTorch compiler that renders FIRST-PARTY templates only and
  never interpolates model-written text into code;
- tensor-shape preflight that rejects incompatible edits before they apply;
- a training/eval adapter behind the standard adapter interface
  (see :mod:`bizora.adapters.torch_adapter`).

Rule Zero holds throughout: layer names, parameter choices, and template
references live in data tables below. The logic is generic validation,
shape arithmetic, and rendering over those tables; it hard-codes no
domain or model names.

Detection signals and entity types are unchanged from v1 so routing keeps
working; only the version, preflight, compilation, and simulator wiring
are new.
"""

from __future__ import annotations

import ast
import keyword
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError

from bizora.contracts.assets import ProceduralKind, ProceduralSpec
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
    RelationKind,
)
from bizora.contracts.packs import (
    CopilotToolSpec,
    DomainTag,
    PackPreflightFinding,
    PackPreflightSeverity,
    PackVocabulary,
    PartRef,
    PartResolution,
    RenderSpec,
    ResolutionConfidence,
    ResolutionLevel,
    SimulationPreview,
    SimulationPreviewSection,
    TelemetryMapping,
)
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.core.entity_registry import EntityTypeDef, InterfaceDef, tokenize
from bizora.packs.lexical import LexicalPack, data_iface, tensor_iface

if TYPE_CHECKING:
    from bizora.contracts.components import ComponentDetail
    from bizora.core.entity_registry import DomainProfile

PACK_ID = "deep-learning"
PACK_VERSION = "2.0.0"
DISPLAY = "Deep learning"
THRESHOLD = 2

# Canonical adapter id for training/eval. The canonical constant lives in
# bizora.adapters.torch_adapter; importing it here would cycle (the adapter
# reuses this pack's compiler), so the string is mirrored and a unit test
# asserts the two stay equal.
TORCH_ADAPTER_ID = "bizora.torch-train"

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
        symbol="embedding",
    ),
    EntityTypeDef(
        "attention-block",
        "Attention block",
        "layer",
        ("attention", "self-attention", "multi-head", "mha"),
        (tensor_iface(),),
        symbol="attention",
    ),
    EntityTypeDef(
        "feedforward-block",
        "Feed-forward block",
        "layer",
        ("feed-forward", "ffn", "mlp", "linear", "dense"),
        (tensor_iface(),),
        symbol="feedforward",
    ),
    EntityTypeDef(
        "normalization",
        "Normalization",
        "layer",
        ("normaliz", "layernorm", "rmsnorm", "batchnorm"),
        (tensor_iface(),),
        symbol="normalization",
    ),
    EntityTypeDef(
        "loss-function",
        "Loss function",
        "compute",
        ("loss", "objective", "cross-entropy", "mse"),
        (tensor_iface(), InterfaceDef("gradients", "tensor")),
        physical=False,
        symbol="loss",
    ),
    EntityTypeDef(
        "optimizer",
        "Optimizer",
        "compute",
        ("optimiz", "adam", "sgd", "scheduler", "learning rate"),
        (InterfaceDef("gradients", "tensor"), InterfaceDef("state", "storage")),
        physical=False,
        symbol="optimizer",
    ),
    EntityTypeDef(
        "dataloader",
        "Data loader",
        "storage",
        ("dataset", "dataloader", "corpus", "shard", "batch", "training"),
        (tensor_iface(),),
        physical=False,
        symbol="dataset",
    ),
    EntityTypeDef(
        "model-evaluator",
        "Model evaluator",
        "compute",
        ("evaluat", "benchmark", "metric", "validation", "test set"),
        (data_iface(),),
        physical=False,
        symbol="evaluator",
    ),
)


# ---------------------------------------------------------------------------
# Allowlisted layer vocabulary (data; Rule Zero: logic below is generic).
# ---------------------------------------------------------------------------

#: A tensor shape; None dims are unknown and act as wildcards. A shape of
#: None means the rank itself is unknown.
Shape = tuple[int | None, ...]

#: Validated parameter values. "block" params normalize to
#: {"layer": <layer_id>, "params": {...}}.
ParamValue = int | float | bool | str | dict[str, Any] | None


@dataclass(frozen=True)
class LayerParamSpec:
    """One parameter of a layer kind: name, scalar kind, bounds, default."""

    name: str
    kind: str  # "int" | "float" | "bool" | "enum" | "block"
    required: bool = True
    default: int | float | bool | str | None = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class LayerConstraint:
    """A structural relation between two numeric parameters of one layer."""

    kind: str  # "divides" | "le" | "lt" | "ge" | "gt" | "eq"
    left: str
    right: str


@dataclass(frozen=True)
class DimCheck:
    """One shape guard: axis ``axis`` must equal param ``param`` when known.

    ``when`` holds (param, value) pairs that must all match for the guard
    to apply, so one layer kind can carry per-variant guards as data.
    """

    axis: int
    param: str
    when: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class LayerSpec:
    """One allowlisted layer kind: shape rule, template, params, constraints."""

    layer_id: str
    display: str
    description: str
    shape_rule: str  # identity | affine_last_dim | append_dim | conv_spatial
    # | pool_spatial | residual
    template_id: str
    params: tuple[LayerParamSpec, ...] = ()
    constraints: tuple[LayerConstraint, ...] = ()
    in_dim_param: str | None = None
    out_dim_param: str | None = None
    channels_in_param: str | None = None
    channels_out_param: str | None = None
    spatial_rank_param: str | None = None
    append_dim_param: str | None = None
    rank_in: tuple[int, ...] | None = None
    dim_checks: tuple[DimCheck, ...] = ()


_ACTIVATION_CHOICES = ("relu", "gelu", "silu", "tanh", "sigmoid", "leaky_relu")


def _int_param(
    name: str,
    *,
    required: bool = True,
    default: int | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> LayerParamSpec:
    return LayerParamSpec(
        name,
        "int",
        required=required,
        default=default,
        minimum=minimum,
        maximum=maximum,
    )


def _float_param(
    name: str,
    *,
    required: bool = True,
    default: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> LayerParamSpec:
    return LayerParamSpec(
        name,
        "float",
        required=required,
        default=default,
        minimum=minimum,
        maximum=maximum,
    )


LAYER_SPECS: tuple[LayerSpec, ...] = (
    LayerSpec(
        layer_id="linear",
        display="Linear",
        description="Affine map over the last dimension.",
        shape_rule="affine_last_dim",
        template_id="linear",
        params=(
            _int_param("in_features", minimum=1),
            _int_param("out_features", minimum=1),
            LayerParamSpec("bias", "bool", required=False, default=True),
        ),
        in_dim_param="in_features",
        out_dim_param="out_features",
    ),
    LayerSpec(
        layer_id="convolution",
        display="Convolution",
        description="N-dimensional convolution over spatial dims.",
        shape_rule="conv_spatial",
        template_id="convolution",
        params=(
            _int_param("in_channels", minimum=1),
            _int_param("out_channels", minimum=1),
            _int_param("spatial_dims", minimum=1, maximum=3),
            _int_param("kernel_size", minimum=1),
            _int_param("stride", required=False, default=1, minimum=1),
            _int_param("padding", required=False, default=0, minimum=0),
            _int_param("dilation", required=False, default=1, minimum=1),
            LayerParamSpec("bias", "bool", required=False, default=True),
        ),
        channels_in_param="in_channels",
        channels_out_param="out_channels",
        spatial_rank_param="spatial_dims",
    ),
    LayerSpec(
        layer_id="normalization",
        display="Normalization",
        description="Shape-preserving normalization.",
        shape_rule="identity",
        template_id="normalization",
        params=(
            LayerParamSpec(
                "variant",
                "enum",
                required=False,
                default="layer",
                choices=("layer", "rms", "group", "batch"),
            ),
            _int_param("num_channels", minimum=1),
            _int_param("num_groups", required=False, default=1, minimum=1),
            _float_param("eps", required=False, default=1e-5, minimum=0.0, maximum=1.0),
        ),
        constraints=(LayerConstraint("divides", "num_channels", "num_groups"),),
        dim_checks=(
            DimCheck(-1, "num_channels", (("variant", "layer"),)),
            DimCheck(-1, "num_channels", (("variant", "rms"),)),
            DimCheck(1, "num_channels", (("variant", "group"),)),
            DimCheck(1, "num_channels", (("variant", "batch"),)),
        ),
    ),
    LayerSpec(
        layer_id="activation",
        display="Activation",
        description="Shape-preserving elementwise activation.",
        shape_rule="identity",
        template_id="activation",
        params=(
            LayerParamSpec(
                "function",
                "enum",
                required=False,
                default="relu",
                choices=_ACTIVATION_CHOICES,
            ),
            _float_param(
                "negative_slope",
                required=False,
                default=0.01,
                minimum=0.0,
                maximum=10.0,
            ),
        ),
    ),
    LayerSpec(
        layer_id="dropout",
        display="Dropout",
        description="Shape-preserving stochastic dropout.",
        shape_rule="identity",
        template_id="dropout",
        params=(_float_param("p", required=False, default=0.1, minimum=0.0, maximum=1.0),),
    ),
    LayerSpec(
        layer_id="attention",
        display="Attention",
        description="Shape-preserving multi-head self-attention (batch-first).",
        shape_rule="identity",
        template_id="attention",
        params=(
            _int_param("embed_dim", minimum=1),
            _int_param("num_heads", minimum=1),
            _float_param("dropout", required=False, default=0.0, minimum=0.0, maximum=1.0),
            LayerParamSpec("bias", "bool", required=False, default=True),
        ),
        constraints=(LayerConstraint("divides", "embed_dim", "num_heads"),),
        rank_in=(2, 3),
    ),
    LayerSpec(
        layer_id="mlp-block",
        display="MLP block",
        description="Two affine maps with an activation and dropout between.",
        shape_rule="affine_last_dim",
        template_id="mlp_block",
        params=(
            _int_param("in_features", minimum=1),
            _int_param("out_features", minimum=1),
            _int_param("hidden_features", minimum=1),
            LayerParamSpec(
                "activation",
                "enum",
                required=False,
                default="gelu",
                choices=_ACTIVATION_CHOICES,
            ),
            _float_param(
                "negative_slope",
                required=False,
                default=0.01,
                minimum=0.0,
                maximum=10.0,
            ),
            _float_param("dropout", required=False, default=0.0, minimum=0.0, maximum=1.0),
            LayerParamSpec("bias", "bool", required=False, default=True),
        ),
        in_dim_param="in_features",
        out_dim_param="out_features",
    ),
    LayerSpec(
        layer_id="residual",
        display="Residual",
        description="Skip connection around one shape-preserving branch block.",
        shape_rule="residual",
        template_id="residual",
        params=(LayerParamSpec("branch", "block"),),
    ),
    LayerSpec(
        layer_id="embedding",
        display="Embedding",
        description="Index lookup appending one feature dimension.",
        shape_rule="append_dim",
        template_id="embedding",
        params=(
            _int_param("num_embeddings", minimum=1),
            _int_param("embedding_dim", minimum=1),
        ),
        append_dim_param="embedding_dim",
    ),
    LayerSpec(
        layer_id="pooling",
        display="Pooling",
        description="Spatial downsampling with preserved channels.",
        shape_rule="pool_spatial",
        template_id="pooling",
        params=(
            _int_param("spatial_dims", minimum=1, maximum=3),
            LayerParamSpec(
                "mode",
                "enum",
                required=False,
                default="max",
                choices=("max", "avg"),
            ),
            _int_param("kernel_size", minimum=1),
            LayerParamSpec(
                "stride",
                "int",
                required=False,
                default=None,
                minimum=1,
            ),
            _int_param("padding", required=False, default=0, minimum=0),
        ),
        spatial_rank_param="spatial_dims",
    ),
    LayerSpec(
        layer_id="positional-encoding",
        display="Positional encoding",
        description="Fixed sinusoidal offsets for (batch, seq, dim) input.",
        shape_rule="identity",
        template_id="positional_encoding",
        params=(
            _int_param("d_model", minimum=1),
            _int_param("max_len", required=False, default=512, minimum=1),
        ),
        rank_in=(3,),
        dim_checks=(DimCheck(-1, "d_model"),),
    ),
)

LAYER_IDS: tuple[str, ...] = tuple(spec.layer_id for spec in LAYER_SPECS)

LAYER_INDEX: dict[str, LayerSpec] = {spec.layer_id: spec for spec in LAYER_SPECS}


def _is_number(value: ParamValue) -> bool:
    """Return whether a validated value is numeric (never a bool)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_range(
    spec: LayerParamSpec,
    value: int | float,
    where: str,
) -> tuple[int | float | None, str | None]:
    """Bound-check one numeric parameter against its spec limits."""
    if spec.minimum is not None and value < spec.minimum:
        return None, (f"{where}: '{spec.name}' is {value}, below minimum {spec.minimum}")
    if spec.maximum is not None and value > spec.maximum:
        return None, (f"{where}: '{spec.name}' is {value}, above maximum {spec.maximum}")
    return value, None


def _validate_scalar(
    spec: LayerParamSpec,
    value: Any,
    where: str,
) -> tuple[ParamValue | None, str | None]:
    """Validate one scalar parameter; block kinds are handled separately."""
    if spec.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return None, f"{where}: '{spec.name}' must be an int"
        return _check_range(spec, value, where)
    if spec.kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, f"{where}: '{spec.name}' must be a number"
        return _check_range(spec, float(value), where)
    if spec.kind == "bool":
        if not isinstance(value, bool):
            return None, f"{where}: '{spec.name}' must be a bool"
        return value, None
    if spec.kind == "enum":
        if not isinstance(value, str) or value not in spec.choices:
            return None, (f"{where}: '{spec.name}' must be one of {', '.join(spec.choices)}")
        return value, None
    raise AssertionError(f"unexpected scalar kind {spec.kind!r}")


def _validate_block(
    value: Any,
    where: str,
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    """Validate one nested branch block against the same allowlist.

    Branches recurse into the same layer table, so only allowlisted kinds
    can appear; a branch may not itself be residual, keeping codegen flat.
    """
    if not isinstance(value, dict):
        return None, (f"{where}: 'branch' must be an object",)
    raw_layer = value.get("layer")
    if not isinstance(raw_layer, str) or raw_layer not in LAYER_INDEX:
        return None, (
            f"{where}: unknown branch layer {raw_layer!r}; expected one of {', '.join(LAYER_IDS)}",
        )
    if raw_layer == "residual":
        return None, (f"{where}: a residual branch may not itself be residual",)
    nested_where = f"{where} branch '{raw_layer}'"
    nested = {key: item for key, item in value.items() if key != "layer"}
    params, errors = validate_layer_params(
        LAYER_INDEX[raw_layer],
        nested,
        where=nested_where,
    )
    if errors:
        return None, errors
    return {"layer": raw_layer, "params": params}, ()


def _check_constraint(
    constraint: LayerConstraint,
    params: dict[str, ParamValue],
    where: str,
) -> str | None:
    """Evaluate one structural parameter constraint; None means satisfied."""
    left = params.get(constraint.left)
    right = params.get(constraint.right)
    if not _is_number(left) or not _is_number(right):
        return None
    left_num = cast(int | float, left)
    right_num = cast(int | float, right)
    satisfied = False
    if constraint.kind == "divides":
        if isinstance(left_num, int) and isinstance(right_num, int):
            satisfied = right_num != 0 and left_num % right_num == 0
        else:
            ratio = left_num / right_num if right_num != 0 else float("nan")
            satisfied = right_num != 0 and abs(ratio - round(ratio)) < 1e-9
    elif constraint.kind == "le":
        satisfied = left_num <= right_num
    elif constraint.kind == "lt":
        satisfied = left_num < right_num
    elif constraint.kind == "ge":
        satisfied = left_num >= right_num
    elif constraint.kind == "gt":
        satisfied = left_num > right_num
    elif constraint.kind == "eq":
        satisfied = left_num == right_num
    else:
        raise AssertionError(f"unexpected constraint {constraint.kind!r}")
    if satisfied:
        return None
    if constraint.kind == "divides":
        return (
            f"{where}: '{constraint.left}' ({left_num}) must be divisible "
            f"by '{constraint.right}' ({right_num})"
        )
    return (
        f"{where}: '{constraint.left}' ({left_num}) violates "
        f"{constraint.kind} '{constraint.right}' ({right_num})"
    )


def validate_layer_params(
    spec: LayerSpec,
    config: Mapping[str, Any],
    *,
    where: str,
) -> tuple[dict[str, ParamValue], tuple[str, ...]]:
    """Validate raw node config against one layer spec.

    Unknown parameters are rejected: nothing model-written may smuggle
    through to codegen. Returns validated params plus error messages.
    """
    errors: list[str] = []
    params: dict[str, ParamValue] = {}
    invalid: set[str] = set()
    by_name = {param.name: param for param in spec.params}
    for name, value in config.items():
        param_spec = by_name.get(name)
        if param_spec is None:
            errors.append(f"{where}: unknown parameter '{name}' for layer '{spec.layer_id}'")
            continue
        if param_spec.kind == "block":
            block, block_errors = _validate_block(value, where)
            errors.extend(block_errors)
            if block is not None:
                params[name] = block
            else:
                invalid.add(name)
            continue
        validated, error = _validate_scalar(param_spec, value, where)
        if error is not None:
            errors.append(error)
            invalid.add(name)
        elif validated is not None:
            params[name] = validated
    for param_spec in spec.params:
        if param_spec.name in params or param_spec.name in invalid:
            continue
        if param_spec.default is not None:
            params[param_spec.name] = param_spec.default
        elif param_spec.required:
            errors.append(
                f"{where}: missing required parameter "
                f"'{param_spec.name}' for layer '{spec.layer_id}'"
            )
    for constraint in spec.constraints:
        failed = _check_constraint(constraint, params, where)
        if failed is not None:
            errors.append(failed)
    return params, tuple(errors)


# ---------------------------------------------------------------------------
# Tensor-shape flow (generic rules over the layer table).
# ---------------------------------------------------------------------------

RULE_SHAPE_MISMATCH = "deep_learning_shape_mismatch"
RULE_UNKNOWN_LAYER = "deep_learning_unknown_layer"
RULE_INVALID_LAYER_PARAMS = "deep_learning_invalid_layer_params"

_SOURCE_KINDS = (NodeKind.INPUT, NodeKind.DATASET)


@dataclass(frozen=True)
class FlowIssue:
    """One shape/binding problem found while flowing tensors through a graph."""

    node_id: str
    rule_id: str
    message: str


@dataclass(frozen=True)
class ShapeFlow:
    """Per-node input/output shapes plus every issue found (empty means clear)."""

    inputs: dict[str, Shape | None]
    outputs: dict[str, Shape | None]
    bindings: dict[str, tuple[str, dict[str, ParamValue]]]
    issues: tuple[FlowIssue, ...]
    order: tuple[str, ...]
    cyclic: bool


def _unify(
    first: Shape | None,
    second: Shape | None,
) -> tuple[Shape | None, str | None]:
    """Merge two shapes; unknown dims are wildcards.

    Returns the merged shape plus a conflict description, or None when the
    shapes agree.
    """
    if first is None:
        return second, None
    if second is None:
        return first, None
    if len(first) != len(second):
        return None, f"rank {len(first)} != rank {len(second)}"
    merged: list[int | None] = []
    for index, (dim_a, dim_b) in enumerate(zip(first, second, strict=True)):
        if dim_a is not None and dim_b is not None and dim_a != dim_b:
            return None, f"dim {index}: {dim_a} != {dim_b}"
        merged.append(dim_a if dim_a is not None else dim_b)
    return tuple(merged), None


def _rule_identity(
    spec: LayerSpec,
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> tuple[Shape | None, tuple[str, ...]]:
    """Flow a shape-preserving layer, enforcing its rank/last-dim guards."""
    if shape is None:
        return None, ()
    if spec.rank_in is not None and len(shape) not in spec.rank_in:
        return None, (
            f"{where}: layer '{spec.layer_id}' expects rank "
            f"in {sorted(spec.rank_in)}, got rank {len(shape)}",
        )
    for check in spec.dim_checks:
        if any(params.get(name) != value for name, value in check.when):
            continue
        axis = check.axis if check.axis >= 0 else len(shape) + check.axis
        if axis < 0 or axis >= len(shape):
            return None, (
                f"{where}: layer '{spec.layer_id}' needs rank > {axis} "
                f"for its '{check.param}' guard, got rank {len(shape)}",
            )
        wanted = cast(int, params[check.param])
        if shape[axis] is not None and shape[axis] != wanted:
            return None, (f"{where}: dim {axis} {shape[axis]} != '{check.param}' {wanted}",)
    return shape, ()


def _rule_affine_last_dim(
    spec: LayerSpec,
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> tuple[Shape | None, tuple[str, ...]]:
    """Flow (..., in) -> (..., out) for affine-style layers."""
    if shape is None:
        return None, ()
    if len(shape) == 0:
        return None, (f"{where}: rank-0 tensor has no feature dimension",)
    in_param = cast(str, spec.in_dim_param)
    out_param = cast(str, spec.out_dim_param)
    wanted_in = cast(int, params[in_param])
    wanted_out = cast(int, params[out_param])
    if shape[-1] is not None and shape[-1] != wanted_in:
        return None, (f"{where}: last dim {shape[-1]} != '{in_param}' {wanted_in}",)
    return (*shape[:-1], wanted_out), ()


def _rule_append_dim(
    spec: LayerSpec,
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> tuple[Shape | None, tuple[str, ...]]:
    """Flow (... ) -> (..., dim) for index-lookup layers."""
    if shape is None:
        return None, ()
    dim_param = cast(str, spec.append_dim_param)
    return (*shape, cast(int, params[dim_param])), ()


def _spatial_output(
    length: int | None,
    kernel: int,
    stride: int,
    padding: int,
    dilation: int,
    where: str,
    index: int,
) -> tuple[int | None, str | None]:
    """Apply the conv/pool spatial formula to one axis (None stays unknown)."""
    if length is None:
        return None, None
    value = (length + 2 * padding - dilation * (kernel - 1) - 1) // stride + 1
    if value <= 0:
        return None, (
            f"{where}: spatial dim {index} length {length} collapses "
            f"(kernel={kernel} stride={stride} padding={padding} "
            f"dilation={dilation})"
        )
    return value, None


def _rule_conv_spatial(
    spec: LayerSpec,
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> tuple[Shape | None, tuple[str, ...]]:
    """Flow (N, C_in, *spatial) -> (N, C_out, *out) for convolution."""
    if shape is None:
        return None, ()
    rank_param = cast(str, spec.spatial_rank_param)
    spatial_dims = cast(int, params[rank_param])
    if len(shape) != 2 + spatial_dims:
        return None, (
            f"{where}: layer '{spec.layer_id}' with {rank_param}="
            f"{spatial_dims} expects rank {2 + spatial_dims}, "
            f"got rank {len(shape)}",
        )
    batch, channels, *spatial = shape
    in_param = cast(str, spec.channels_in_param)
    wanted_in = cast(int, params[in_param])
    if channels is not None and channels != wanted_in:
        return None, (f"{where}: input channels {channels} != '{in_param}' {wanted_in}",)
    kernel = cast(int, params["kernel_size"])
    stride = cast(int, params["stride"])
    padding = cast(int, params["padding"])
    dilation = cast(int, params["dilation"])
    outputs: list[int | None] = []
    for index, length in enumerate(spatial):
        value, error = _spatial_output(
            length,
            kernel,
            stride,
            padding,
            dilation,
            where,
            index,
        )
        if error is not None:
            return None, (error,)
        outputs.append(value)
    out_param = cast(str, spec.channels_out_param)
    return (batch, cast(int, params[out_param]), *outputs), ()


def _rule_pool_spatial(
    spec: LayerSpec,
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> tuple[Shape | None, tuple[str, ...]]:
    """Flow (N, C, *spatial) -> (N, C, *out) for pooling (channels kept)."""
    if shape is None:
        return None, ()
    rank_param = cast(str, spec.spatial_rank_param)
    spatial_dims = cast(int, params[rank_param])
    if len(shape) != 2 + spatial_dims:
        return None, (
            f"{where}: layer '{spec.layer_id}' with {rank_param}="
            f"{spatial_dims} expects rank {2 + spatial_dims}, "
            f"got rank {len(shape)}",
        )
    batch, channels, *spatial = shape
    kernel = cast(int, params["kernel_size"])
    stride_raw = params.get("stride")
    stride = cast(int, stride_raw) if stride_raw is not None else kernel
    padding = cast(int, params["padding"])
    outputs: list[int | None] = []
    for index, length in enumerate(spatial):
        value, error = _spatial_output(
            length,
            kernel,
            stride,
            padding,
            1,
            where,
            index,
        )
        if error is not None:
            return None, (error,)
        outputs.append(value)
    return (batch, channels, *outputs), ()


def _rule_residual(
    spec: LayerSpec,
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> tuple[Shape | None, tuple[str, ...]]:
    """Flow a residual block: the branch must preserve the block input."""
    del spec
    if shape is None:
        return None, ()
    branch = cast(dict[str, Any], params["branch"])
    branch_layer = cast(str, branch["layer"])
    branch_params = cast(dict[str, ParamValue], branch["params"])
    branch_spec = LAYER_INDEX[branch_layer]
    branch_where = f"{where} branch '{branch_layer}'"
    branch_out, errors = _apply_shape_rule(
        branch_spec,
        branch_params,
        shape,
        branch_where,
    )
    if errors:
        return None, errors
    merged, conflict = _unify(shape, branch_out)
    if conflict is not None:
        return None, (
            f"{where}: residual branch output conflicts with the block input ({conflict})",
        )
    return merged, ()


def _apply_shape_rule(
    spec: LayerSpec,
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> tuple[Shape | None, tuple[str, ...]]:
    """Dispatch one layer's shape rule; the table picks the rule, not logic."""
    rule = spec.shape_rule
    if rule == "identity":
        return _rule_identity(spec, params, shape, where)
    if rule == "affine_last_dim":
        return _rule_affine_last_dim(spec, params, shape, where)
    if rule == "append_dim":
        return _rule_append_dim(spec, params, shape, where)
    if rule == "conv_spatial":
        return _rule_conv_spatial(spec, params, shape, where)
    if rule == "pool_spatial":
        return _rule_pool_spatial(spec, params, shape, where)
    if rule == "residual":
        return _rule_residual(spec, params, shape, where)
    raise AssertionError(f"unknown shape rule {rule!r}")


def _flow_order(
    node_ids: Sequence[str],
    edges: Sequence[GraphEdge],
) -> tuple[tuple[str, ...], bool]:
    """Topologically order data-flow targets; report when cyclic."""
    successors: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        if edge.source not in indegree or edge.target not in indegree:
            continue
        successors[edge.source].append(edge.target)
        indegree[edge.target] += 1
    queue = [node_id for node_id in node_ids if indegree[node_id] == 0]
    order: list[str] = []
    while queue:
        current = queue.pop(0)
        order.append(current)
        for target in successors[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(order) != len(node_ids):
        return tuple(node_ids), True
    return tuple(order), False


def infer_shape_flow(
    nodes: Sequence[GraphNode],
    edges: Sequence[GraphEdge],
) -> ShapeFlow:
    """Flow tensor shapes along data-flow edges and collect every issue.

    Nodes whose config names an allowlisted ``layer`` are validated and
    flowed through that layer's rule. Source nodes (input/dataset) seed
    shapes from their declared fields; every other unbound node passes its
    input through, so preflight only rejects demonstrable conflicts and
    never guesses about opaque components.
    """
    by_id = {node.id: node for node in nodes}
    data_edges = [
        edge
        for edge in edges
        if edge.relation == RelationKind.DATA_FLOW and edge.source in by_id and edge.target in by_id
    ]
    predecessors: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in data_edges:
        if edge.source not in predecessors[edge.target]:
            predecessors[edge.target].append(edge.source)
    order, cyclic = _flow_order([node.id for node in nodes], data_edges)

    bindings: dict[str, tuple[str, dict[str, ParamValue]]] = {}
    issues: list[FlowIssue] = []
    for node in nodes:
        raw_layer = node.config.get("layer")
        if raw_layer is None:
            continue
        where = f"node '{node.id}'"
        if not isinstance(raw_layer, str) or raw_layer not in LAYER_INDEX:
            issues.append(
                FlowIssue(
                    node.id,
                    RULE_UNKNOWN_LAYER,
                    f"{where}: unknown layer {raw_layer!r}; expected one of {', '.join(LAYER_IDS)}",
                )
            )
            continue
        spec = LAYER_INDEX[raw_layer]
        nested = {key: value for key, value in node.config.items() if key != "layer"}
        params, errors = validate_layer_params(spec, nested, where=where)
        for error in errors:
            issues.append(FlowIssue(node.id, RULE_INVALID_LAYER_PARAMS, error))
        if not errors:
            bindings[node.id] = (raw_layer, params)

    inputs: dict[str, Shape | None] = {}
    outputs: dict[str, Shape | None] = {}
    for node_id in order:
        node = by_id[node_id]
        merged: Shape | None = node.input_shape
        for predecessor in predecessors[node_id]:
            candidate = outputs.get(predecessor)
            merged, conflict = _unify(merged, candidate)
            if conflict is not None:
                issues.append(
                    FlowIssue(
                        node_id,
                        RULE_SHAPE_MISMATCH,
                        f"node '{node_id}' has conflicting inputs ({conflict})",
                    )
                )
                merged = None
                break
        inputs[node_id] = merged
        binding = bindings.get(node_id)
        if binding is not None:
            layer_id, params = binding
            where = f"node '{node_id}'"
            inferred, rule_errors = _apply_shape_rule(
                LAYER_INDEX[layer_id],
                params,
                merged,
                where,
            )
            for error in rule_errors:
                issues.append(FlowIssue(node_id, RULE_SHAPE_MISMATCH, error))
            declared = node.output_shape
            if declared is not None and inferred is not None:
                unified, conflict = _unify(inferred, declared)
                if conflict is not None:
                    issues.append(
                        FlowIssue(
                            node_id,
                            RULE_SHAPE_MISMATCH,
                            f"node '{node_id}' declared output conflicts with "
                            f"its inferred shape ({conflict})",
                        )
                    )
                    outputs[node_id] = None
                else:
                    outputs[node_id] = unified
            elif declared is not None:
                outputs[node_id] = declared
            else:
                outputs[node_id] = inferred
        elif node.kind in _SOURCE_KINDS:
            declared = node.output_shape
            seed = node.input_shape
            if declared is not None and seed is not None:
                unified, conflict = _unify(declared, seed)
                if conflict is not None:
                    issues.append(
                        FlowIssue(
                            node_id,
                            RULE_SHAPE_MISMATCH,
                            f"node '{node_id}' declared input conflicts with "
                            f"its declared output ({conflict})",
                        )
                    )
                    outputs[node_id] = None
                else:
                    outputs[node_id] = unified
            else:
                outputs[node_id] = declared if declared is not None else seed
        else:
            declared = node.output_shape
            if declared is not None and merged is not None:
                unified, conflict = _unify(merged, declared)
                if conflict is not None:
                    issues.append(
                        FlowIssue(
                            node_id,
                            RULE_SHAPE_MISMATCH,
                            f"node '{node_id}' declared output conflicts with "
                            f"its input ({conflict})",
                        )
                    )
                    outputs[node_id] = None
                else:
                    outputs[node_id] = unified
            else:
                outputs[node_id] = declared if declared is not None else merged
    return ShapeFlow(
        inputs=inputs,
        outputs=outputs,
        bindings=bindings,
        issues=tuple(issues),
        order=order,
        cyclic=cyclic,
    )


# ---------------------------------------------------------------------------
# First-party PyTorch templates. Generated code references ONLY these plus
# torch APIs; check_first_party_source() enforces that structurally.
# ---------------------------------------------------------------------------

_RMS_NORM_HELPER = '''class _RMSNorm(nn.Module):
    """Root-mean-square normalization over the last dimension."""

    def __init__(self, dim: int, eps: float = 1e-05) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.ones(dim))
        self.eps = eps

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        variance = torch.mean(x * x, dim=-1, keepdim=True)
        return x * torch.rsqrt(variance + self.eps) * self.weight
'''

_RESIDUAL_HELPER = '''class _Residual(nn.Module):
    """Skip connection around one shape-preserving branch."""

    def __init__(self, branch: nn.Module) -> None:
        super().__init__()
        self.branch = branch

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.branch(x)
'''

_POSITIONAL_HELPER = '''class _SinusoidalPositionalEncoding(nn.Module):
    """Fixed sinusoidal offsets for (batch, seq, dim) input."""

    def __init__(self, d_model: int, max_len: int = 512) -> None:
        super().__init__()
        positions = torch.arange(0, max_len).unsqueeze(1)
        divterm = torch.exp(torch.arange(0, d_model, 2) * -(math.log(10000.0) / d_model))
        table = torch.zeros(max_len, d_model)
        table[:, 0::2] = torch.sin(positions * divterm)
        table[:, 1::2] = torch.cos(positions * divterm)
        self.register_buffer("pe", table.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[:, : x.size(1)]
'''

#: Preamble helper id -> fixed first-party source. Helpers ship only when a
#: rendered layer needs them; their ids join the compiled template record.
_PREAMBLE_HELPERS: dict[str, str] = {
    "rms_norm": _RMS_NORM_HELPER,
    "residual": _RESIDUAL_HELPER,
    "positional": _POSITIONAL_HELPER,
}

_HELPER_CLASS_NAMES = {
    "_RMSNorm",
    "_Residual",
    "_SinusoidalPositionalEncoding",
}

_ACTIVATION_CTORS: dict[str, str] = {
    "relu": "nn.ReLU()",
    "gelu": "nn.GELU()",
    "silu": "nn.SiLU()",
    "tanh": "nn.Tanh()",
    "sigmoid": "nn.Sigmoid()",
}

_CONV_CTORS = {1: "nn.Conv1d", 2: "nn.Conv2d", 3: "nn.Conv3d"}
_MAX_POOL_CTORS = {1: "nn.MaxPool1d", 2: "nn.MaxPool2d", 3: "nn.MaxPool3d"}
_AVG_POOL_CTORS = {1: "nn.AvgPool1d", 2: "nn.AvgPool2d", 3: "nn.AvgPool3d"}
_BATCH_NORM_CTORS = {
    2: "nn.BatchNorm1d",
    3: "nn.BatchNorm1d",
    4: "nn.BatchNorm2d",
    5: "nn.BatchNorm3d",
}


class _RenderError(ValueError):
    """One layer failed to render; the compiler collects these honestly."""

    def __init__(self, where: str, message: str) -> None:
        self.where = where
        super().__init__(f"{where}: {message}")


@dataclass(frozen=True)
class RenderedLayer:
    """One rendered constructor expression plus needed preamble helpers."""

    construct: str
    helpers: tuple[str, ...] = ()


def _activation_ctor(name: str, slope: float) -> str:
    """Return the fixed constructor for one allowlisted activation name."""
    if name == "leaky_relu":
        return f"nn.LeakyReLU({slope!r})"
    return _ACTIVATION_CTORS[name]


def _render_linear(
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    del shape, where
    in_dim = cast(int, params["in_features"])
    out_dim = cast(int, params["out_features"])
    bias = cast(bool, params["bias"])
    return RenderedLayer(f"nn.Linear({in_dim!r}, {out_dim!r}, bias={bias!r})")


def _render_convolution(
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    del shape, where
    ctor = _CONV_CTORS[cast(int, params["spatial_dims"])]
    in_ch = cast(int, params["in_channels"])
    out_ch = cast(int, params["out_channels"])
    kernel = cast(int, params["kernel_size"])
    stride = cast(int, params["stride"])
    padding = cast(int, params["padding"])
    dilation = cast(int, params["dilation"])
    bias = cast(bool, params["bias"])
    return RenderedLayer(
        f"{ctor}({in_ch!r}, {out_ch!r}, kernel_size={kernel!r}, "
        f"stride={stride!r}, padding={padding!r}, dilation={dilation!r}, "
        f"bias={bias!r})"
    )


def _render_normalization(
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    variant = cast(str, params["variant"])
    channels = cast(int, params["num_channels"])
    groups = cast(int, params["num_groups"])
    eps = cast(float, params["eps"])
    if variant == "layer":
        return RenderedLayer(f"nn.LayerNorm({channels!r}, eps={eps!r})")
    if variant == "rms":
        return RenderedLayer(
            f"_RMSNorm({channels!r}, eps={eps!r})",
            ("rms_norm",),
        )
    if variant == "group":
        return RenderedLayer(
            f"nn.GroupNorm({groups!r}, {channels!r}, eps={eps!r})",
        )
    if shape is None:
        raise _RenderError(
            where,
            "batch normalization needs a known input rank; "
            "declare input/output shapes on the graph",
        )
    ctor = _BATCH_NORM_CTORS.get(len(shape))
    if ctor is None:
        raise _RenderError(
            where,
            f"batch normalization supports ranks 2-5, got rank {len(shape)}",
        )
    return RenderedLayer(f"{ctor}({channels!r}, eps={eps!r})")


def _render_activation(
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    del shape, where
    name = cast(str, params["function"])
    slope = cast(float, params["negative_slope"])
    return RenderedLayer(_activation_ctor(name, slope))


def _render_dropout(
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    del shape, where
    return RenderedLayer(f"nn.Dropout({cast(float, params['p'])!r})")


def _render_attention(
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    del shape, where
    embed = cast(int, params["embed_dim"])
    heads = cast(int, params["num_heads"])
    dropout = cast(float, params["dropout"])
    bias = cast(bool, params["bias"])
    return RenderedLayer(
        f"nn.MultiheadAttention({embed!r}, {heads!r}, dropout={dropout!r}, "
        f"bias={bias!r}, batch_first=True)"
    )


def _render_mlp_block(
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    del shape, where
    in_dim = cast(int, params["in_features"])
    out_dim = cast(int, params["out_features"])
    hidden = cast(int, params["hidden_features"])
    activation = _activation_ctor(
        cast(str, params["activation"]),
        cast(float, params["negative_slope"]),
    )
    dropout = cast(float, params["dropout"])
    bias = cast(bool, params["bias"])
    return RenderedLayer(
        f"nn.Sequential(nn.Linear({in_dim!r}, {hidden!r}, bias={bias!r}), "
        f"{activation}, nn.Dropout({dropout!r}), "
        f"nn.Linear({hidden!r}, {out_dim!r}, bias={bias!r}))"
    )


def _render_residual(
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    branch = cast(dict[str, Any], params["branch"])
    branch_layer = cast(str, branch["layer"])
    branch_params = cast(dict[str, ParamValue], branch["params"])
    inner = _render_template(
        LAYER_INDEX[branch_layer].template_id,
        branch_params,
        shape,
        f"{where} branch '{branch_layer}'",
    )
    helpers = (*inner.helpers, "residual") if "residual" not in inner.helpers else inner.helpers
    return RenderedLayer(f"_Residual({inner.construct})", helpers)


def _render_embedding(
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    del shape, where
    num = cast(int, params["num_embeddings"])
    dim = cast(int, params["embedding_dim"])
    return RenderedLayer(f"nn.Embedding({num!r}, {dim!r})")


def _render_pooling(
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    del shape, where
    spatial_dims = cast(int, params["spatial_dims"])
    mode = cast(str, params["mode"])
    ctor = _MAX_POOL_CTORS[spatial_dims] if mode == "max" else _AVG_POOL_CTORS[spatial_dims]
    kernel = cast(int, params["kernel_size"])
    stride_raw = params.get("stride")
    stride = cast(int, stride_raw) if stride_raw is not None else kernel
    padding = cast(int, params["padding"])
    return RenderedLayer(f"{ctor}(kernel_size={kernel!r}, stride={stride!r}, padding={padding!r})")


def _render_positional_encoding(
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    del shape, where
    dim = cast(int, params["d_model"])
    max_len = cast(int, params["max_len"])
    return RenderedLayer(
        f"_SinusoidalPositionalEncoding({dim!r}, max_len={max_len!r})",
        ("positional",),
    )


_LayerRenderer = Callable[
    [dict[str, ParamValue], Shape | None, str],
    RenderedLayer,
]

_TEMPLATE_RENDERERS: dict[str, _LayerRenderer] = {
    "linear": _render_linear,
    "convolution": _render_convolution,
    "normalization": _render_normalization,
    "activation": _render_activation,
    "dropout": _render_dropout,
    "attention": _render_attention,
    "mlp_block": _render_mlp_block,
    "residual": _render_residual,
    "embedding": _render_embedding,
    "pooling": _render_pooling,
    "positional_encoding": _render_positional_encoding,
}


def _render_template(
    template_id: str,
    params: dict[str, ParamValue],
    shape: Shape | None,
    where: str,
) -> RenderedLayer:
    """Render one template by id; unknown ids are wiring bugs, not input."""
    renderer = _TEMPLATE_RENDERERS.get(template_id)
    if renderer is None:
        raise AssertionError(f"no renderer for template {template_id!r}")
    return renderer(params, shape, where)


# ---------------------------------------------------------------------------
# Structural validation: generated code references only first-party templates.
# ---------------------------------------------------------------------------

_TORCH_ATTRS = frozenset(
    {
        "Tensor",
        "zeros",
        "ones",
        "arange",
        "exp",
        "sin",
        "cos",
        "mean",
        "rsqrt",
    }
)

_NN_ATTRS = frozenset(
    {
        "Module",
        "Parameter",
        "Linear",
        "Conv1d",
        "Conv2d",
        "Conv3d",
        "MaxPool1d",
        "MaxPool2d",
        "MaxPool3d",
        "AvgPool1d",
        "AvgPool2d",
        "AvgPool3d",
        "Embedding",
        "Dropout",
        "MultiheadAttention",
        "Sequential",
        "LayerNorm",
        "GroupNorm",
        "BatchNorm1d",
        "BatchNorm2d",
        "BatchNorm3d",
        "ReLU",
        "GELU",
        "SiLU",
        "Tanh",
        "Sigmoid",
        "LeakyReLU",
    }
)

_MATH_ATTRS = frozenset({"log"})

_TENSOR_ATTRS = frozenset({"unsqueeze", "size"})

_GLOBAL_NAMES = frozenset({"torch", "nn", "math", "self", "super"})

_BUILTIN_NAMES = frozenset({"int", "float", "bool", "str"})

_ALLOWED_METHODS = frozenset({"__init__", "forward"})

_ALLOWED_NODE_TYPES = frozenset(
    {
        ast.Module,
        ast.ClassDef,
        ast.FunctionDef,
        ast.arguments,
        ast.arg,
        ast.Expr,
        ast.Assign,
        ast.Return,
        ast.Call,
        ast.keyword,
        ast.Attribute,
        ast.Name,
        ast.Constant,
        ast.Tuple,
        ast.List,
        ast.BinOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.UnaryOp,
        ast.USub,
        ast.UAdd,
        ast.Subscript,
        ast.Slice,
        ast.Load,
        ast.Store,
        ast.Import,
        ast.ImportFrom,
        ast.alias,
    }
)


def _check_template_import(node: ast.Import | ast.ImportFrom) -> str | None:
    """Restrict imports to the torch/math surface the templates need."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.asname is not None or alias.name not in {"torch", "math"}:
                return f"import {alias.name!r} is outside the first-party template surface"
        return None
    if node.level != 0 or node.module != "torch":
        return f"from-import {node.module!r} is outside the first-party template surface"
    for alias in node.names:
        if alias.asname is not None or alias.name != "nn":
            return f"from-import {alias.name!r} is outside the first-party template surface"
    return None


def _check_template_class(node: ast.ClassDef) -> tuple[str, ...]:
    """Restrict class definitions to plain nn.Module subclasses."""
    findings: list[str] = []
    if (
        not node.name.isidentifier()
        or keyword.iskeyword(node.name)
        or (node.name.startswith("_") and node.name not in _HELPER_CLASS_NAMES)
    ):
        findings.append(f"class {node.name!r} is not template output")
    if node.decorator_list:
        findings.append(f"class {node.name!r} must not use decorators")
    bases = node.bases
    if (
        len(bases) != 1
        or not isinstance(bases[0], ast.Attribute)
        or not isinstance(bases[0].value, ast.Name)
        or bases[0].value.id != "nn"
        or bases[0].attr != "Module"
    ):
        findings.append(f"class {node.name!r} must extend nn.Module")
    for statement in node.body:
        if isinstance(statement, ast.FunctionDef):
            continue
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        findings.append(
            f"class {node.name!r} body holds {type(statement).__name__}, not template output"
        )
    return tuple(findings)


def _check_template_name(
    node: ast.Name,
    locals_: frozenset[str],
    defined: frozenset[str],
) -> str | None:
    """Restrict loaded names to torch, locals, and defined classes."""
    if not isinstance(node.ctx, ast.Load):
        return None
    if (
        node.id in _GLOBAL_NAMES
        or node.id in _BUILTIN_NAMES
        or node.id in locals_
        or node.id in defined
    ):
        return None
    return f"name {node.id!r} is outside the first-party template surface"


def _check_template_attribute(node: ast.Attribute) -> str | None:
    """Restrict attribute access by receiver kind."""
    value = node.value
    if isinstance(value, ast.Name) and value.id == "torch":
        allowed = node.attr in _TORCH_ATTRS
    elif isinstance(value, ast.Name) and value.id == "nn":
        allowed = node.attr in _NN_ATTRS
    elif isinstance(value, ast.Name) and value.id == "math":
        allowed = node.attr in _MATH_ATTRS
    elif isinstance(value, ast.Name) and value.id == "self":
        allowed = True
    elif (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "super"
    ):
        allowed = node.attr == "__init__"
    else:
        allowed = node.attr in _TENSOR_ATTRS
    if allowed:
        return None
    return f"attribute {node.attr!r} is outside the first-party template surface"


def check_first_party_source(source: str) -> tuple[str, ...]:
    """Validate that source references only first-party templates.

    Default-deny over the AST: imports, names, attributes, node types, and
    class shapes must all fall inside the fixed template surface. Empty
    means clean; anything else lists violations for the caller to refuse.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return (f"generated source is not valid Python: {exc}",)
    violations: list[str] = []
    defined = frozenset(node.name for node in tree.body if isinstance(node, ast.ClassDef))
    local_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arg):
            local_names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            local_names.add(node.id)
    locals_ = frozenset(local_names)
    for statement in tree.body:
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            failure = _check_template_import(statement)
            if failure is not None:
                violations.append(failure)
            continue
        if isinstance(statement, ast.ClassDef):
            continue
        violations.append(f"module statement {type(statement).__name__} is not template output")
    mains = [name for name in defined if name not in _HELPER_CLASS_NAMES]
    if len(mains) != 1:
        violations.append(
            "generated source must define exactly one model class",
        )
    methods: dict[str, set[str]] = {name: set() for name in defined}
    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODE_TYPES:
            violations.append(f"{type(node).__name__} is outside the first-party template surface")
            continue
        if isinstance(node, ast.ClassDef):
            violations.extend(_check_template_class(node))
        elif isinstance(node, ast.FunctionDef):
            if node.name not in _ALLOWED_METHODS:
                violations.append(f"method {node.name!r} is outside the template surface")
            if node.decorator_list:
                violations.append(f"method {node.name!r} must not use decorators")
            arguments = node.args
            if arguments.vararg is not None or arguments.kwarg is not None or arguments.kwonlyargs:
                violations.append(f"method {node.name!r} must not take variadic arguments")
        elif isinstance(node, ast.Name):
            failure = _check_template_name(node, locals_, defined)
            if failure is not None:
                violations.append(failure)
        elif isinstance(node, ast.Attribute):
            failure = _check_template_attribute(node)
            if failure is not None:
                violations.append(failure)
        elif isinstance(node, ast.Call) and not isinstance(node.func, (ast.Name, ast.Attribute)):
            violations.append("indirect calls are outside the template surface")
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for statement in node.body:
                if isinstance(statement, ast.FunctionDef):
                    methods[node.name].add(statement.name)
    for name in mains:
        missing = _ALLOWED_METHODS - methods.get(name, set())
        if missing:
            violations.append(
                f"model class {name!r} is missing {sorted(missing)}",
            )
    return tuple(violations)


# ---------------------------------------------------------------------------
# Graph-to-PyTorch compiler (templates only; never model-written code).
# ---------------------------------------------------------------------------

MAX_COMPILE_ERRORS = 16


class GraphCompileError(ValueError):
    """A graph cannot compile: carries every reason found, bounded."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors) if self.errors else "graph compilation failed")


@dataclass(frozen=True)
class CompiledLayer:
    """One compiled layer: node binding, template, and helper provenance."""

    node_id: str
    layer_id: str
    template_id: str
    attribute: str
    helpers: tuple[str, ...]


@dataclass(frozen=True)
class CompiledModule:
    """One compiled graph: validated source plus its template record."""

    module_name: str
    source: str
    template_ids: tuple[str, ...]
    layers: tuple[CompiledLayer, ...]
    shapes: dict[str, Shape | None]
    entry_shape: Shape | None
    entry_layer_id: str
    entry_vocab: int | None


def _concrete_int(value: ParamValue) -> int | None:
    """Return a validated int param, or None when absent/non-int."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def compile_graph_to_torch(
    graph: MethodologyGraph,
    *,
    module_name: str = "DeepLearningModel",
) -> CompiledModule:
    """Compile data-flow layer nodes into a validated torch module.

    Only nodes bound to the allowlisted vocabulary (via config ``layer``)
    become layers; sources and sinks only seed shapes. Labels, descriptions,
    and node ids never reach the emitted code: identifiers are generated
    (``layer_0`` ...) and every constructor comes from a first-party
    template over validated scalars.
    """
    if not module_name.isidentifier() or keyword.iskeyword(module_name):
        raise GraphCompileError([f"invalid module name {module_name!r}"])
    flow = infer_shape_flow(graph.nodes, graph.edges)
    if flow.issues:
        raise GraphCompileError(
            [issue.message for issue in flow.issues[:MAX_COMPILE_ERRORS]],
        )
    if flow.cyclic:
        raise GraphCompileError(
            ["graph contains a data-flow cycle; compilation needs a DAG"],
        )
    bound = [
        (node_id, *flow.bindings[node_id]) for node_id in flow.order if node_id in flow.bindings
    ]
    if not bound:
        raise GraphCompileError(
            [
                "graph has no nodes bound to the layer vocabulary "
                f"(set node config 'layer' to one of {', '.join(LAYER_IDS)})"
            ],
        )
    rendered: list[RenderedLayer] = []
    layers: list[CompiledLayer] = []
    for index, (node_id, layer_id, params) in enumerate(bound):
        spec = LAYER_INDEX[layer_id]
        where = f"node '{node_id}'"
        try:
            built = _render_template(
                spec.template_id,
                params,
                flow.inputs[node_id],
                where,
            )
        except _RenderError as exc:
            raise GraphCompileError([str(exc)]) from exc
        rendered.append(built)
        layers.append(
            CompiledLayer(
                node_id=node_id,
                layer_id=layer_id,
                template_id=spec.template_id,
                attribute=f"layer_{index}",
                helpers=built.helpers,
            )
        )
    helpers_used = sorted({name for layer in rendered for name in layer.helpers})
    provenance = ", ".join(LAYER_INDEX[layer_id].template_id for _, layer_id, _ in bound)
    lines = [
        '"""First-party generated PyTorch module. Do not edit by hand.',
        "",
        "Produced by bizora.packs.deep_learning from allowlisted templates",
        f"only ({provenance}).",
        '"""',
        "import torch",
        "from torch import nn",
    ]
    if "positional" in helpers_used:
        lines.append("import math")
    lines.append("")
    lines.append("")
    for helper_id in helpers_used:
        lines.append(_PREAMBLE_HELPERS[helper_id].rstrip("\n"))
        lines.append("")
        lines.append("")
    lines.append(f"class {module_name}(nn.Module):")
    lines.append(f'    """Feed-forward stack of {len(layers)} template layers."""')
    lines.append("")
    lines.append("    def __init__(self) -> None:")
    lines.append("        super().__init__()")
    for layer, rendered_layer in zip(layers, rendered, strict=True):
        lines.append(f"        self.{layer.attribute} = {rendered_layer.construct}")
    lines.append("")
    lines.append("    def forward(self, x: torch.Tensor) -> torch.Tensor:")
    for layer in layers:
        lines.append(f"        x = self.{layer.attribute}(x)")
    lines.append("        return x")
    lines.append("")
    source = "\n".join(lines)
    violations = check_first_party_source(source)
    if violations:
        raise GraphCompileError(
            [f"compiler self-check failed: {item}" for item in violations],
        )
    template_ids = tuple(layer.template_id for layer in layers) + tuple(
        f"helper:{name}" for name in helpers_used
    )
    entry_id, entry_layer, entry_params = bound[0]
    entry_vocab: int | None = None
    if entry_layer == "embedding":
        entry_vocab = _concrete_int(entry_params.get("num_embeddings"))
    return CompiledModule(
        module_name=module_name,
        source=source,
        template_ids=template_ids,
        layers=tuple(layers),
        shapes=dict(flow.outputs),
        entry_shape=flow.inputs[entry_id],
        entry_layer_id=entry_layer,
        entry_vocab=entry_vocab,
    )


# ---------------------------------------------------------------------------
# Patch preflight: reject shape-incompatible edits before they apply.
# ---------------------------------------------------------------------------

MAX_PREFLIGHT_FINDINGS = 16


def _hypothetical_nodes_edges(
    graph: MethodologyGraph,
    patch: GraphPatch,
) -> tuple[list[GraphNode], list[GraphEdge]] | None:
    """Apply one patch hypothetically; None means the core owns the verdict.

    Structural problems (stale base, unparseable payloads, missing targets,
    duplicate ids, removing connected nodes) belong to the patch service,
    so preflight abstains and lets that layer report them.
    """
    if patch.base_graph_id != graph.graph_id or patch.base_version != graph.version:
        return None
    nodes = list(graph.nodes)
    edges = list(graph.edges)
    operation = patch.operation
    if operation in (PatchOperation.ADD_NODE, PatchOperation.REPLACE_NODE):
        raw = patch.payload.get("node")
        if not isinstance(raw, dict):
            return None
        try:
            node = GraphNode.model_validate(raw)
        except ValidationError:
            return None
        if operation is PatchOperation.ADD_NODE:
            if any(existing.id == node.id for existing in nodes):
                return None
            nodes.append(node)
        else:
            if patch.target_id is None or node.id != patch.target_id:
                return None
            index = next(
                (pos for pos, existing in enumerate(nodes) if existing.id == patch.target_id),
                None,
            )
            if index is None:
                return None
            nodes[index] = node
    elif operation is PatchOperation.UPDATE_NODE_CONFIG:
        if patch.target_id is None:
            return None
        raw_config = patch.payload.get("config")
        if not isinstance(raw_config, dict):
            return None
        index = next(
            (pos for pos, existing in enumerate(nodes) if existing.id == patch.target_id),
            None,
        )
        if index is None:
            return None
        merged = {**nodes[index].config, **raw_config}
        node_data = nodes[index].model_dump(mode="python")
        node_data["config"] = merged
        try:
            nodes[index] = GraphNode.model_validate(node_data)
        except ValidationError:
            return None
    elif operation is PatchOperation.ADD_EDGE:
        raw_edge = patch.payload.get("edge")
        if not isinstance(raw_edge, dict):
            return None
        try:
            edge = GraphEdge.model_validate(raw_edge)
        except ValidationError:
            return None
        if any(existing.id == edge.id for existing in edges):
            return None
        known = {node.id for node in nodes}
        if edge.source not in known or edge.target not in known:
            return None
        edges.append(edge)
    elif operation is PatchOperation.REMOVE_EDGE:
        if patch.target_id is None:
            return None
        index = next(
            (pos for pos, existing in enumerate(edges) if existing.id == patch.target_id),
            None,
        )
        if index is None:
            return None
        edges.pop(index)
    elif operation is PatchOperation.REMOVE_NODE:
        if patch.target_id is None:
            return None
        if not any(node.id == patch.target_id for node in nodes):
            return None
        if any(edge.source == patch.target_id or edge.target == patch.target_id for edge in edges):
            return None
        nodes = [node for node in nodes if node.id != patch.target_id]
    else:
        return None
    return nodes, edges


def preflight_patch(
    graph: MethodologyGraph,
    patch: GraphPatch,
) -> tuple[PackPreflightFinding, ...]:
    """Return BLOCK findings for shape-incompatible edits; empty means clear."""
    hypothetical = _hypothetical_nodes_edges(graph, patch)
    if hypothetical is None:
        return ()
    nodes, edges = hypothetical
    flow = infer_shape_flow(nodes, edges)
    return tuple(
        PackPreflightFinding(
            rule_id=issue.rule_id,
            severity=PackPreflightSeverity.BLOCK,
            message=issue.message[:2000],
        )
        for issue in flow.issues[:MAX_PREFLIGHT_FINDINGS]
    )


# ---------------------------------------------------------------------------
# Layer resolution and tensor-shape geometry for the 3D explorer.
# ---------------------------------------------------------------------------

#: Namespace pinning layer resolutions apart from catalog asset keys.
_LAYER_ASSET_PREFIX = "layer:"

#: Slab footprint when the config states no usable dims (millimetres).
_DEFAULT_SLAB_MM = 10.0

#: Fixed slab thickness; per-layer dims drive width and height only.
_SLAB_THICKNESS_MM = 8.0


def _match_layer_id(raw_text: str) -> str | None:
    """Return the first layer kind named by the text, if any.

    Matches need a whole layer-id token ("mlp-block") or a whole
    display phrase ("MLP block"), so "Attention block" resolves while
    partial words never match. Single common words can still match
    ("attention" in "pay attention"), which is why layer resolutions
    stay at MATCHED confidence (representative, not exact).
    """
    tokens = set(tokenize(raw_text))
    lowered = raw_text.lower()
    for spec in LAYER_SPECS:
        if spec.layer_id in tokens or spec.display.lower() in lowered:
            return spec.layer_id
    return None


def _layer_of(resolution: PartResolution) -> str | None:
    """Return the layer id behind a layer resolution, or None."""
    key = resolution.asset_key
    if (
        resolution.level is not ResolutionLevel.CATEGORY
        or key is None
        or not key.startswith(_LAYER_ASSET_PREFIX)
    ):
        return None
    layer_id = key[len(_LAYER_ASSET_PREFIX):]
    return layer_id if layer_id in LAYER_INDEX else None


def _dim_mm(value: object) -> float | None:
    """Scale one positive config int to millimetres, or None when unusable.

    Log scaling keeps a 768-wide embedding visibly larger than a
    12-head attention block without letting vocab sizes explode the
    scene; bools and non-ints fall back to the default slab.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return min(60.0, max(2.0, 2.0 + 6.0 * math.log10(1.0 + value)))


def _layer_box_dims(layer_id: str, config: Mapping[str, Any]) -> tuple[float, float]:
    """Return (width, height) for one layer from its declared dim params.

    Width follows the output dim, height the input dim; layers without
    declared dims fall back to required int params in spec order (ranks
    and other small-range params excluded), then to the default slab.
    """
    spec = LAYER_INDEX[layer_id]
    width_keys = [
        key
        for key in (spec.out_dim_param, spec.channels_out_param, spec.append_dim_param)
        if key is not None
    ]
    height_keys = [
        key for key in (spec.in_dim_param, spec.channels_in_param) if key is not None
    ]
    fallback = [
        param.name
        for param in spec.params
        if param.kind == "int"
        and param.required
        and (param.maximum is None or param.maximum > 16)
    ]
    width: float | None = None
    width_key: str | None = None
    for key in [*width_keys, *fallback]:
        sized = _dim_mm(config.get(key))
        if sized is not None:
            width, width_key = sized, key
            break
    height: float | None = None
    for key in [*height_keys, *fallback]:
        if key == width_key:
            continue
        sized = _dim_mm(config.get(key))
        if sized is not None:
            height = sized
            break
    return (
        width if width is not None else _DEFAULT_SLAB_MM,
        height if height is not None else _DEFAULT_SLAB_MM,
    )


# ---------------------------------------------------------------------------
# The pack: lexical routing plus shape preflight and compilation.
# ---------------------------------------------------------------------------


class DeepLearningPack:
    """Phase-6 ML/DL pack behind the DomainPack/ProfiledPack protocols.

    Detection delegates to the generic lexical harness over unchanged
    v1 data; resolution and rendering match the layer vocabulary first
    (compiler bindings, then label mentions) and fall back to the
    harness; preflight adds tensor-shape verdicts, and :meth:`compile`
    exposes the template-only PyTorch compiler.
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
            # torch-train exists but cannot execute anywhere yet (no torch
            # locally, no Modal credentials, local runner refuses ISOLATED),
            # so the pack honestly reports no runnable adapters. Flip this
            # together with default-registry registration when execution lands.
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

    @property
    def layers(self) -> tuple[LayerSpec, ...]:
        """Return the allowlisted layer vocabulary."""
        return LAYER_SPECS

    def detect(self, tags: tuple[DomainTag, ...]) -> float:
        """Score pack affinity: matched signals over the open-vocabulary tags."""
        return self._lexical.detect(tags)

    def resolve_part(self, ref: PartRef) -> PartResolution:
        """Resolve compiler-bound or named layers, else the lexical ladder."""
        bound = ref.parameters.get("layer", "").strip()
        if bound and bound in LAYER_INDEX:
            return PartResolution(
                level=ResolutionLevel.CATEGORY,
                confidence=ResolutionConfidence.MATCHED,
                pack_id=PACK_ID,
                kind_id=bound,
                asset_key=f"{_LAYER_ASSET_PREFIX}{bound}",
                reason=f"Node binds compiler layer '{bound}'.",
            )
        matched = _match_layer_id(ref.raw_text)
        if matched is not None:
            display = LAYER_INDEX[matched].display
            return PartResolution(
                level=ResolutionLevel.CATEGORY,
                confidence=ResolutionConfidence.MATCHED,
                pack_id=PACK_ID,
                kind_id=matched,
                asset_key=f"{_LAYER_ASSET_PREFIX}{matched}",
                reason=f"Label mentions {display}; treat as representative, not exact.",
            )
        return self._lexical.resolve_part(ref)

    def render_spec(self, resolution: PartResolution) -> RenderSpec:
        """Label layer resolutions with the layer display name."""
        layer_id = _layer_of(resolution)
        if layer_id is not None:
            return RenderSpec(label=LAYER_INDEX[layer_id].display, illustrative=True)
        return self._lexical.render_spec(resolution)

    def procedural_spec(
        self, node_config: Mapping[str, Any], resolution: PartResolution
    ) -> tuple[ProceduralSpec, ...]:
        """Return the tensor-shape slab for one layer, or () otherwise."""
        layer_id = _layer_of(resolution)
        if layer_id is None:
            return ()
        width_mm, height_mm = _layer_box_dims(layer_id, node_config)
        return (
            ProceduralSpec(
                kind=ProceduralKind.BOX,
                body_length_mm=width_mm,
                body_width_mm=_SLAB_THICKNESS_MM,
                body_height_mm=height_mm,
                pin_count=0,
            ),
        )

    def check_patch(
        self,
        graph: MethodologyGraph,
        patch: GraphPatch,
    ) -> tuple[PackPreflightFinding, ...]:
        """Block interface-dropping swaps and shape-incompatible edits."""
        lexical = self._lexical.check_patch(graph, patch)
        shapes = preflight_patch(graph, patch)
        return (*lexical, *shapes)

    def compile(
        self,
        graph: MethodologyGraph,
        *,
        module_name: str = "DeepLearningModel",
    ) -> CompiledModule:
        """Compile graph layers to a validated torch module (see compiler)."""
        return compile_graph_to_torch(graph, module_name=module_name)

    def simulation_preview(self, graph: MethodologyGraph) -> SimulationPreview | None:
        """Summarize compiled layers and shapes; compile errors become warnings."""
        bound = [node for node in graph.nodes if node.config.get("layer")]
        if not bound:
            return None
        try:
            compiled = compile_graph_to_torch(graph)
        except GraphCompileError as exc:
            return SimulationPreview(
                pack_id=PACK_ID,
                title="PyTorch module preview",
                sections=(),
                warnings=tuple(error[:500] for error in exc.errors),
            )
        layer_lines = [
            f"{layer.layer_id} ({layer.template_id}): "
            f"{compiled.shapes.get(layer.node_id)}"
            for layer in compiled.layers
        ]
        source_lines = compiled.source.splitlines()
        truncated = source_lines[:120]
        if len(source_lines) > len(truncated):
            truncated = [
                *truncated,
                f"... ({len(source_lines) - len(truncated)} more lines)",
            ]
        return SimulationPreview(
            pack_id=PACK_ID,
            title="PyTorch module preview",
            sections=(
                SimulationPreviewSection(
                    heading=f"Layers ({len(compiled.layers)})",
                    lines=tuple(layer_lines),
                ),
                SimulationPreviewSection(
                    heading=f"Generated source ({compiled.module_name})",
                    lines=tuple(truncated),
                ),
            ),
            warnings=(),
        )

    def telemetry_mapping(self) -> TelemetryMapping | None:
        """Return None: no pack maps live telemetry yet (Stage 2)."""
        return self._lexical.telemetry_mapping()


pack = DeepLearningPack()
