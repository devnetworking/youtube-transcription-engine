"""Document Processing Workspace: PDF -> Markdown, merge, split.

A self-contained module reusing the same conventions as the rest of the
project (Pydantic models, a staged pipeline with a `report` callback,
config via YAML + env vars, thread-based background jobs) rather than
introducing a second architecture. See README.md, section "Document
Processing", for an overview.
"""
