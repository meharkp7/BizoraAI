"""Distributed systems pack: services and infrastructure.

Catalog entries and detection profile moved verbatim from the former
core registry into pack data, wired to the generic pack harness.
"""

from typing import Any

from bizora.core.entity_registry import EntityTypeDef, InterfaceDef
from bizora.packs.lexical import LexicalPack, data_iface

DATA = {"name": "data", "kind": "data", "params": {}}
CONTROL = {"name": "control", "kind": "protocol", "params": {}}
PROTO = {"name": "requests", "kind": "protocol", "params": {}}

COMPONENTS: list[dict[str, Any]] = [
    {
        "component_id": "svc-client-generic",
        "domain": "distributed-systems",
        "entity_type": "client",
        "category": "service",
        "kind": "input",
        "label": "API client (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic workload-generating client",
        "description": (
            "Generic client issuing requests against the system under study. "
            "Set the workload shape for load experiments."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [PROTO],
        "constraints": {},
        "config_schema": [
            {
                "key": "request_rate_rps",
                "label": "Request rate",
                "type": "number",
                "default": 100,
                "unit": "rps",
                "required": False,
                "description": "Offered load in requests per second.",
            },
        ],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "svc-coordinator-generic",
        "domain": "distributed-systems",
        "entity_type": "coordinator",
        "category": "service",
        "kind": "component",
        "label": "Cluster coordinator (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic scheduling and coordination service",
        "description": (
            "Generic coordinator assigning work and tracking cluster state. "
            "No exact scheduler is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [CONTROL, DATA],
        "constraints": {},
        "config_schema": [
            {
                "key": "replicas",
                "label": "Replicas",
                "type": "number",
                "default": 1,
                "required": False,
                "description": "Coordinator replica count.",
            },
        ],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "svc-worker-generic",
        "domain": "distributed-systems",
        "entity_type": "worker",
        "category": "service",
        "kind": "component",
        "label": "Task worker (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic task-executing worker",
        "description": (
            "Generic worker executing tasks assigned by the coordinator. "
            "Set the worker pool size for scaling studies."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [CONTROL, DATA],
        "constraints": {},
        "config_schema": [
            {
                "key": "pool_size",
                "label": "Pool size",
                "type": "number",
                "default": 4,
                "required": False,
                "description": "Number of worker replicas behind this node.",
            },
        ],
        "default_config": {"pool_size": 4},
        "evidence": [],
    },
    {
        "component_id": "store-postgres-16",
        "domain": "distributed-systems",
        "entity_type": "storage-node",
        "category": "storage",
        "kind": "dataset",
        "label": "PostgreSQL 16 database",
        "generic": False,
        "manufacturer": "PostgreSQL Global Development Group",
        "part_number": "PostgreSQL 16",
        "headline": "Relational storage node with streaming replication",
        "description": (
            "PostgreSQL 16 as the durable storage node, with streaming replication "
            "to the replica for fault-recovery studies."
        ),
        "datasheet_url": None,
        "reference_url": "https://www.postgresql.org/docs/",
        "specs": [
            {"name": "Version", "value": "16", "typical": False},
            {"name": "Replication", "value": "streaming", "typical": False},
        ],
        "pinout": [],
        "interfaces": [
            {"name": "store", "kind": "storage", "params": {}},
            {"name": "replication", "kind": "replication", "params": {}},
        ],
        "constraints": {},
        "config_schema": [
            {
                "key": "version",
                "label": "Version",
                "type": "string",
                "default": "16",
                "required": True,
                "description": "Exact major version recorded on the node.",
            },
            {
                "key": "synchronous_commit",
                "label": "Synchronous commit",
                "type": "boolean",
                "default": False,
                "required": False,
                "description": "Wait for replica acknowledgement on commit.",
            },
        ],
        "default_config": {"version": "16"},
        "evidence": [
            {
                "source": "PostgreSQL documentation",
                "note": "Verified reference URL.",
            },
        ],
    },
    {
        "component_id": "store-replica-generic",
        "domain": "distributed-systems",
        "entity_type": "storage-node",
        "category": "storage",
        "kind": "dataset",
        "label": "Storage replica (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic read replica for fault recovery",
        "description": (
            "Generic storage replica consuming the replication stream. "
            "No exact database is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [
            {"name": "store", "kind": "storage", "params": {}},
            {"name": "replication", "kind": "replication", "params": {}},
        ],
        "constraints": {},
        "config_schema": [],
        "default_config": {},
        "evidence": [],
    },
    {
        "component_id": "queue-kafka-3",
        "domain": "distributed-systems",
        "entity_type": "message-queue",
        "category": "network",
        "kind": "component",
        "label": "Apache Kafka message broker",
        "generic": False,
        "manufacturer": "Apache Software Foundation",
        "part_number": "Kafka 3",
        "headline": "Distributed log broker with publish/subscribe topics",
        "description": (
            "Apache Kafka 3 as the durable message broker between producers and "
            "consumers. Set the topic and retention for the workload."
        ),
        "datasheet_url": None,
        "reference_url": "https://kafka.apache.org/documentation/",
        "specs": [
            {"name": "Version", "value": "3", "typical": False},
            {"name": "Model", "value": "publish/subscribe log", "typical": False},
        ],
        "pinout": [],
        "interfaces": [
            {"name": "publish", "kind": "protocol", "params": {}},
            {"name": "subscribe", "kind": "protocol", "params": {}},
        ],
        "constraints": {},
        "config_schema": [
            {
                "key": "version",
                "label": "Version",
                "type": "string",
                "default": "3",
                "required": True,
                "description": "Exact major version recorded on the node.",
            },
            {
                "key": "topic",
                "label": "Topic",
                "type": "string",
                "default": "events",
                "required": True,
                "description": "Topic carrying this workload.",
            },
        ],
        "default_config": {"version": "3", "topic": "events"},
        "evidence": [
            {
                "source": "Apache Kafka documentation",
                "note": "Verified reference URL.",
            },
        ],
    },
    {
        "component_id": "lb-proxy-generic",
        "domain": "distributed-systems",
        "entity_type": "load-balancer",
        "category": "network",
        "kind": "component",
        "label": "Reverse proxy load balancer (generic)",
        "generic": True,
        "manufacturer": None,
        "part_number": None,
        "headline": "Generic frontend/backend traffic distributor",
        "description": (
            "Generic reverse-proxy load balancer spreading client traffic across "
            "workers. No exact proxy is implied."
        ),
        "datasheet_url": None,
        "reference_url": None,
        "specs": [{"name": "Identity", "value": "generic", "typical": False}],
        "pinout": [],
        "interfaces": [
            {"name": "frontend", "kind": "protocol", "params": {}},
            {"name": "backend", "kind": "protocol", "params": {}},
        ],
        "constraints": {},
        "config_schema": [
            {
                "key": "algorithm",
                "label": "Algorithm",
                "type": "enum",
                "default": "round-robin",
                "options": ["round-robin", "least-connections", "ip-hash"],
                "required": True,
                "description": "Backend selection algorithm.",
            },
        ],
        "default_config": {"algorithm": "round-robin"},
        "evidence": [],
    },
]


PACK_ID = "distributed-systems"
PACK_VERSION = "1.0.0"
DISPLAY = "Distributed systems"
THRESHOLD = 2

SIGNALS: tuple[str, ...] = (
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
)

ENTITY_TYPES: tuple[EntityTypeDef, ...] = (
    EntityTypeDef(
        "client",
        "Client",
        "service",
        ("client", "frontend", "cli", "sdk"),
        (InterfaceDef("requests", "protocol"),),
        symbol="client",
    ),
    EntityTypeDef(
        "coordinator",
        "Coordinator",
        "service",
        ("coordinator", "leader", "master", "scheduler", "controller", "gateway"),
        (InterfaceDef("control", "protocol"), data_iface()),
        symbol="coordinator",
    ),
    EntityTypeDef(
        "worker",
        "Worker",
        "service",
        ("worker", "executor", "task", "follower", "agent"),
        (InterfaceDef("control", "protocol"), data_iface()),
        symbol="worker",
    ),
    EntityTypeDef(
        "storage-node",
        "Storage node",
        "storage",
        ("storage", "database", "shard", "disk", "sst", "wal", "log", "cache"),
        (InterfaceDef("store", "storage"), InterfaceDef("replication", "replication")),
        symbol="storage",
    ),
    EntityTypeDef(
        "message-queue",
        "Message queue",
        "network",
        ("queue", "broker", "kafka", "stream", "pubsub", "topic"),
        (InterfaceDef("publish", "protocol"), InterfaceDef("subscribe", "protocol")),
        symbol="queue",
    ),
    EntityTypeDef(
        "load-balancer",
        "Load balancer",
        "network",
        ("load balanc", "proxy", "router", "ingress"),
        (InterfaceDef("frontend", "protocol"), InterfaceDef("backend", "protocol")),
        symbol="load-balancer",
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
