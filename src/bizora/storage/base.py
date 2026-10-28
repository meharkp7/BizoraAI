"""Backend-neutral object-store interface and key conventions.

Keys are namespaced as ``<namespace>/<project_id>/<object_name>`` so PDFs,
figures, artifacts, and 3D assets stay separated without embedding any
domain, paper, or part knowledge in the path logic.
"""

import re
from typing import Protocol, runtime_checkable

from bizora.contracts.storage import ObjectNamespace, StoredObject
from bizora.core.errors import BizoraError, ErrorCode

_SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_MAX_OBJECT_NAME_PARTS = 8


class ObjectStorageError(BizoraError):
    """Raised when a storage backend request fails."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.PROVIDER_REQUEST_FAILED, message)


class ObjectNotFoundError(BizoraError):
    """Raised when a requested object key does not exist."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.RESOURCE_NOT_FOUND, message)


@runtime_checkable
class ObjectStore(Protocol):
    """Interface implemented by every object-storage backend."""

    def put_object(
        self, key: str, data: bytes, content_type: str
    ) -> StoredObject:
        """Store bytes at a key, overwriting any previous value."""
        ...

    def get_object(self, key: str) -> bytes:
        """Return an object's bytes or raise ObjectNotFoundError."""
        ...

    def stat_object(self, key: str) -> StoredObject:
        """Return an object's metadata or raise ObjectNotFoundError."""
        ...

    def delete_object(self, key: str) -> None:
        """Remove an object; missing keys are a silent no-op."""
        ...

    def object_exists(self, key: str) -> bool:
        """Return whether an object exists at a key."""
        ...


def build_object_key(
    namespace: ObjectNamespace,
    project_id: str,
    object_name: str,
) -> str:
    """Build a validated ``<namespace>/<project>/<name>`` storage key."""
    if not _SEGMENT_PATTERN.fullmatch(project_id):
        raise BizoraError(
            ErrorCode.INVALID_REQUEST,
            "Project id must be 1-128 chars of letters, digits, '.', '_' or '-'.",
        )
    parts = object_name.split("/")
    if not 1 <= len(parts) <= _MAX_OBJECT_NAME_PARTS:
        raise BizoraError(
            ErrorCode.INVALID_REQUEST,
            "Object name must have 1-8 '/'-separated segments.",
        )
    for part in parts:
        if not _SEGMENT_PATTERN.fullmatch(part) or part in (".", ".."):
            raise BizoraError(
                ErrorCode.INVALID_REQUEST,
                "Object name segments must be 1-128 chars of letters, "
                "digits, '.', '_' or '-', without traversal.",
            )
    return f"{namespace.value}/{project_id}/{object_name}"
