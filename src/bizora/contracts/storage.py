"""Object-storage contracts for PDFs, figures, artifacts, and 3D assets.

Large binaries live in S3-compatible object storage, never in database
rows. These contracts describe object references and stored-object
metadata; transport backends live in :mod:`bizora.storage`.
"""

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class ObjectNamespace(StrEnum):
    """Top-level key prefix segment for one content category."""

    PDFS = "pdfs"
    FIGURES = "figures"
    ARTIFACTS = "artifacts"
    ASSETS = "assets"


class ObjectRef(BaseModel):
    """Bucket plus key locating one stored object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bucket: str = Field(min_length=1, max_length=63)
    key: str = Field(min_length=1, max_length=1024)

    @field_validator("key")
    @classmethod
    def validate_key_shape(cls, value: str) -> str:
        """Reject absolute keys, traversal segments, and separators."""
        if value.startswith("/") or "\\" in value:
            raise ValueError("Object key must be relative and use '/' separators.")
        if any(segment in ("", ".", "..") for segment in value.split("/")):
            raise ValueError("Object key must not contain empty or traversal segments.")
        return value


class StoredObject(BaseModel):
    """Metadata recorded when an object is written to storage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bucket: str = Field(min_length=1, max_length=63)
    key: str = Field(min_length=1, max_length=1024)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    content_type: str = Field(min_length=1, max_length=128)

    @field_validator("key")
    @classmethod
    def validate_key_shape(cls, value: str) -> str:
        """Apply the same key rules as :class:`ObjectRef`."""
        return ObjectRef(bucket="placeholder", key=value).key


class PresignedDownload(BaseModel):
    """A time-limited direct-download URL for one stored object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str = Field(min_length=1, max_length=2048)
    expires_at: AwareDatetime

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, value: str) -> str:
        """Require an HTTP(S) URL."""
        if not value.startswith(("https://", "http://")):
            raise ValueError("Presigned URL must start with http:// or https://.")
        return value
