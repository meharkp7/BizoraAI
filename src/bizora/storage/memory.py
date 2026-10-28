"""In-memory object store.

TEST/DEV-ONLY FAKE: values live in a plain dict, nothing is durable,
and contents vanish with the process. Production must use
:class:`bizora.storage.s3.S3ObjectStore`.
"""

import hashlib

from bizora.contracts.storage import ObjectRef, StoredObject
from bizora.storage.base import ObjectNotFoundError


class InMemoryObjectStore:
    """Dict-backed fake implementing the ObjectStore protocol."""

    def __init__(self, bucket: str = "fake-bucket") -> None:
        self._bucket = bucket
        self._objects: dict[str, tuple[bytes, str]] = {}

    def put_object(
        self, key: str, data: bytes, content_type: str
    ) -> StoredObject:
        """Store bytes after validating the key shape."""
        ObjectRef(bucket=self._bucket, key=key)
        self._objects[key] = (bytes(data), content_type)
        return self.stat_object(key)

    def get_object(self, key: str) -> bytes:
        """Return stored bytes or raise ObjectNotFoundError."""
        try:
            data, _ = self._objects[key]
        except KeyError:
            raise ObjectNotFoundError(
                f"Object '{key}' does not exist."
            ) from None
        return bytes(data)

    def stat_object(self, key: str) -> StoredObject:
        """Return stored metadata or raise ObjectNotFoundError."""
        try:
            data, content_type = self._objects[key]
        except KeyError:
            raise ObjectNotFoundError(
                f"Object '{key}' does not exist."
            ) from None
        return StoredObject(
            bucket=self._bucket,
            key=key,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            content_type=content_type,
        )

    def delete_object(self, key: str) -> None:
        """Remove an object; missing keys are a silent no-op."""
        self._objects.pop(key, None)

    def object_exists(self, key: str) -> bool:
        """Return whether an object exists at a key."""
        return key in self._objects
