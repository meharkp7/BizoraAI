# Architecture and service boundaries

## Product loop

1. **Ingest** a user-authorized paper and retain immutable source identity.
2. **Extract** text, tables, equations, figures, and page geometry into source artifacts.
3. **Propose** methodology nodes and edges using model providers; all claims retain provenance and evidence locators.
4. **Validate and version** the graph. A graph revision is immutable; changes are declarative patches against a known base revision.
5. **Explore** the graph in the UI and open the supporting source excerpt beside each claim.
6. **Compile** supported patches into a registered adapter configuration; reject unsupported edits before queueing.
7. **Execute** only approved adapter jobs in a resource-limited isolated worker.
8. **Record and compare** metrics, logs, artifacts, environment, dataset revision, random seed, code revision, and graph version.

## Logical components

- Web client: project workspace, source viewer, graph explorer/editor, evidence panel, experiment comparison, research chat.
- API: authentication/authorization, project lifecycle, upload metadata, graph versions, patch validation, experiment submission and status.
- Domain contracts: provider-neutral Pydantic schemas shared across boundaries.
- Ingestion workers: PDF parsing and figure/equation extraction; isolated from experiment workers.
- Intelligence adapters: model-provider clients, structured extraction, segmentation, evidence alignment. Providers are replaceable behind interfaces.
- Graph engine: invariants, patch application, version lineage, compatibility checks.
- Compiler/adapter registry: allowlisted architectures and operations only; first target is a Hugging Face Vision Transformer classification path.
- Experiment workers: ephemeral, quota-limited jobs; no arbitrary generated code execution; network disabled by default.
- Persistence: relational metadata store for projects/versions/runs; object storage for PDFs, datasets, checkpoints, logs, and result artifacts. Do not put large binaries in relational rows.
- Queue and observability: idempotent job dispatch, retry policy, structured logs, metrics, trace/run IDs, timeout and cancellation.

## State and data ownership

- Graph versions are append-only. `parent_version` points to the prior revision.
- Every patch names `base_graph_id` and `base_version`; stale patches must fail with a conflict rather than silently overwrite a newer graph.
- Experiment configuration snapshots a graph version and dataset revision at submission time.
- Result records are immutable once finalized; corrections create a new result revision with an audit trail.
- The paper is evidence, not executable authority. A paper's code snippets or uploaded files must never be executed directly.

## Initial scope boundaries

**In scope first:** one feed-forward vision-transformer classification workflow, one existing open-source implementation adapter, one small public dataset configuration, graph validation, evidence-linked explanations, measured evaluation, baseline/variant comparison.

**Not in initial slice:** arbitrary model/code generation, unrestricted shell execution, arbitrary Python plugins, multi-user enterprise tenancy, real-time collaboration, support for every research domain, guaranteed paper reproduction, and 3D rendering before the core workflow is validated.
