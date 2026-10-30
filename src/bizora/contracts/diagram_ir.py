"""Diagram intermediate representations (IRs) consumed by the diagram engine.

Three IRs are defined here:

- CircuitIR: a transcribed schematic (components, nets, ports).
- MethodologyIR: a transcribed methodology flow (groups, nodes, edges).
- StructureIR: a transcribed physical structure (a tree of nested blocks).

All coordinates are normalized: x right, y down, 0-100 over the figure.

These contracts enforce shape only (types, enums, ranges). Semantic
cross-reference checks (id uniqueness, pin/net references, required pins)
live in bizora.core.diagram_validation so validators can report every
problem at once instead of failing fast at parse time.
"""

from enum import StrEnum
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

IR_VERSION: Final = 1

CIRCUIT_IR_SCHEMA_NAME = "circuit_ir"
METHODOLOGY_IR_SCHEMA_NAME = "methodology_ir"
STRUCTURE_IR_SCHEMA_NAME = "structure_ir"

NormalizedCoord = Annotated[float, Field(ge=0, le=100)]
Confidence = Annotated[float, Field(ge=0, le=1)]
NormalizedBBox = Annotated[
    list[NormalizedCoord], Field(min_length=4, max_length=4)
]


class ComponentType(StrEnum):
    NMOS = "nmos"
    PMOS = "pmos"
    RESISTOR = "resistor"
    CAPACITOR = "capacitor"
    INDUCTOR = "inductor"
    DIODE = "diode"
    VSOURCE = "vsource"
    ISOURCE = "isource"
    GROUND = "ground"
    INVERTER = "inverter"
    BUFFER = "buffer"
    AMP = "amp"
    COMPARATOR = "comparator"
    BLOCK = "block"


class NetRole(StrEnum):
    SUPPLY = "supply"
    GROUND = "ground"
    SIGNAL = "signal"
    CLOCK = "clock"
    INPUT = "input"
    OUTPUT = "output"


class PortDirection(StrEnum):
    IN = "in"
    OUT = "out"
    INOUT = "inout"


class Side(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


class CircuitPlacement(BaseModel):
    """Normalized placement of a component within the figure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x: NormalizedCoord
    y: NormalizedCoord
    rot: Literal[0, 90, 180, 270] = 0
    mirror: bool = False
    flip: bool = False


class XYPlacement(BaseModel):
    """Normalized point placement (ports, structure blocks)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x: NormalizedCoord
    y: NormalizedCoord


class CircuitEvidence(BaseModel):
    """Where in the figure a component was transcribed from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    figure_id: str = Field(min_length=1, max_length=128)
    bbox: NormalizedBBox | None = Field(default=None)
    quote: str | None = Field(default=None, max_length=2000)


class CircuitComponent(BaseModel):
    """One transcribed schematic symbol."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    type: ComponentType
    label: str = Field(min_length=1, max_length=256)
    value: str | None = Field(default=None, max_length=128)
    pins: dict[str, str] = Field(description="Pin name -> net id.")
    pin_sides: dict[str, Side] | None = Field(
        default=None, description="Block only: pin name -> side it exits on."
    )
    placement: CircuitPlacement | None = Field(default=None)
    confidence: Confidence
    evidence: CircuitEvidence | None = Field(default=None)


class CircuitNet(BaseModel):
    """One electrical net connecting component pins."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=256)
    role: NetRole
    is_global: bool = Field(alias="global")


class CircuitPort(BaseModel):
    """One external connection point of the circuit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    net: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=256)
    dir: PortDirection
    side: Side
    placement: XYPlacement | None = Field(default=None)


class CircuitSource(BaseModel):
    """Figure the circuit was transcribed from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    figure_id: str = Field(min_length=1, max_length=128)
    page: int = Field(ge=1)


class SubCircuit(BaseModel):
    """Named group of components drawn as one subcircuit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=256)
    component_ids: tuple[str, ...] = ()


class CircuitLayout(BaseModel):
    """Figure-level layout hints for the renderer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    unit: float | None = Field(default=None)


class CircuitIR(BaseModel):
    """Transcribed schematic consumed by the diagram engine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    title: str = Field(min_length=1, max_length=512)
    source: CircuitSource
    components: tuple[CircuitComponent, ...]
    nets: tuple[CircuitNet, ...]
    ports: tuple[CircuitPort, ...]
    subcircuits: tuple[SubCircuit, ...] = ()
    layout: CircuitLayout | None = Field(default=None)


class MethodologyNodeKind(StrEnum):
    INPUT = "input"
    PROCESS = "process"
    DECISION = "decision"
    STORE = "store"
    MODEL = "model"
    EVALUATION = "evaluation"
    DATASET = "dataset"
    OUTPUT = "output"


class MethodologyEdgeKind(StrEnum):
    DATA = "data"
    CONTROL = "control"
    FEEDBACK = "feedback"


class MethodologyGroup(BaseModel):
    """Named (optionally nested) swimlane of methodology nodes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=256)
    parent: str | None = Field(default=None, max_length=128)


class MethodologyEvidence(BaseModel):
    """Text or figure location a node was transcribed from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page: int | None = Field(default=None, ge=1)
    figure_id: str | None = Field(default=None, max_length=128)
    quote: str | None = Field(default=None, max_length=2000)


class MethodologyNode(BaseModel):
    """One step in the methodology flow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=512)
    kind: MethodologyNodeKind
    group: str | None = Field(default=None, max_length=128)
    detail: str | None = Field(default=None, max_length=2000)
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: Confidence
    evidence: MethodologyEvidence | None = Field(default=None)


class MethodologyEdge(BaseModel):
    """One connection between methodology nodes."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    from_node: str = Field(min_length=1, max_length=128, alias="from")
    to: str = Field(min_length=1, max_length=128)
    label: str | None = Field(default=None, max_length=256)
    kind: MethodologyEdgeKind = MethodologyEdgeKind.DATA


class MethodologyIR(BaseModel):
    """Transcribed methodology flow consumed by the diagram engine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    title: str = Field(min_length=1, max_length=512)
    groups: tuple[MethodologyGroup, ...]
    nodes: tuple[MethodologyNode, ...]
    edges: tuple[MethodologyEdge, ...]


class BlockKind(StrEnum):
    CHIP = "chip"
    ARRAY = "array"
    CELL = "cell"
    PERIPHERY = "periphery"
    MODULE = "module"
    BOARD = "board"
    LAYER = "layer"
    PART = "part"
    REGION = "region"


class BlockPosition(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
    CENTER = "center"


class ArrayCount(BaseModel):
    """Row/column repetition count of an array block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: int
    cols: int


class BlockDims(BaseModel):
    """Physical dimensions of a structure block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    w: float | None = Field(default=None)
    h: float | None = Field(default=None)
    d: float | None = Field(default=None)
    unit: str | None = Field(default=None, max_length=32)


class StructureEvidence(BaseModel):
    """Text or figure location a block was transcribed from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page: int | None = Field(default=None, ge=1)
    figure_id: str | None = Field(default=None, max_length=128)
    quote: str | None = Field(default=None, max_length=2000)


class StructureBlock(BaseModel):
    """One node of the physical-structure tree.

    An array's first child is the repeated cell; count gives rows x cols
    (or a flat repetition count when given as an integer).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=512)
    kind: BlockKind
    count: int | ArrayCount | None = Field(default=None)
    dims: BlockDims | None = Field(default=None)
    pos: BlockPosition | XYPlacement | None = Field(default=None)
    part: str | None = Field(default=None, max_length=128)
    tensor_shape: list[int] | None = Field(default=None)
    children: tuple["StructureBlock", ...] = ()
    confidence: Confidence
    evidence: StructureEvidence | None = Field(default=None)


class StructureIR(BaseModel):
    """Transcribed physical structure consumed by the diagram engine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    title: str = Field(min_length=1, max_length=512)
    root: StructureBlock


CIRCUIT_IR_JSON_SCHEMA: dict[str, Any] = CircuitIR.model_json_schema()
METHODOLOGY_IR_JSON_SCHEMA: dict[str, Any] = MethodologyIR.model_json_schema()
STRUCTURE_IR_JSON_SCHEMA: dict[str, Any] = StructureIR.model_json_schema()


def diagram_json_schemas() -> dict[str, dict[str, Any]]:
    """Return the exported JSON Schemas keyed by schema name."""
    return {
        CIRCUIT_IR_SCHEMA_NAME: CIRCUIT_IR_JSON_SCHEMA,
        METHODOLOGY_IR_SCHEMA_NAME: METHODOLOGY_IR_JSON_SCHEMA,
        STRUCTURE_IR_SCHEMA_NAME: STRUCTURE_IR_JSON_SCHEMA,
    }
