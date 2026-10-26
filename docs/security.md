# Security baseline

- Treat paper text, PDFs, figures, uploaded datasets, repository contents, and model output as untrusted input.
- Enforce upload size/type limits; parse documents in isolated workers; defend against archive bombs, malformed PDFs, path traversal, and parser resource exhaustion.
- Validate all graph patches against a known graph revision and a strict schema. Reject unknown operation types and unknown adapter parameters.
- Never run arbitrary code emitted by an LLM or copied from a paper/repository.
- Experiment jobs run in ephemeral sandboxes with explicit resource quotas, timeouts, restricted filesystem access, and network disabled by default.
- Store provider credentials only in environment/secret management; never return them to the browser or include them in logs.
- Use authorization checks on every project, source, dataset, graph, and run access; do not rely on opaque IDs as authorization.
- Record audit events for graph edits, experiment submissions, cancellations, and artifact access.
- Retain dataset licensing and provenance metadata; do not assume a public download is licensed for every use.
