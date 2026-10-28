"""Tests for the S3-compatible object-storage interface.

All S3 signing tests run offline with clearly-marked fake credentials;
HTTP behavior is exercised through an in-memory transport, never the
network. A live round-trip against a real S3-compatible service is NOT
covered here.
"""

import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import quote

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from pytest import MonkeyPatch

from bizora.contracts.storage import (
    ObjectNamespace,
    ObjectRef,
    PresignedDownload,
    StoredObject,
)
from bizora.core.errors import BizoraError, ConfigurationError, ErrorCode
from bizora.storage.base import (
    ObjectNotFoundError,
    ObjectStorageError,
    ObjectStore,
    build_object_key,
)
from bizora.storage.memory import InMemoryObjectStore
from bizora.storage.s3 import (
    S3ObjectStore,
    S3Settings,
    presigned_get_url,
    sign_v4_headers,
)

FAKE_KEY = "FAKEACCESSKEY"
FAKE_SECRET = "FAKESECRETKEY"
FIXED_NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)

# Golden vector pinning the header-signing output for fixed inputs.
GOLDEN_AUTHORIZATION = (
    "AWS4-HMAC-SHA256 Credential=FAKEKEY/20261028/us-east-1/s3/aws4_request, "
    "SignedHeaders=host;x-amz-content-sha256;x-amz-date, "
    "Signature=324a2ff905f4d20cd3e4b67bd99adf675b603e9567352b64a2f4450ac739da79"
)
GOLDEN_PRESIGNATURE = (
    "3b616a9191db4c1e6bf41117b028b2f18a698d71dadc7104da02720cf9ce7e39"
)


def _independent_header_signature(
    *,
    method: str,
    path: str,
    host: str,
    payload_hash: str,
    access_key: str,
    secret: str,
) -> str:
    """Recompute a SigV4 signature straight from the documented steps."""
    amz_date = "20261028T120000Z"
    scope = "20261028/us-east-1/s3/aws4_request"
    canonical = (
        f"{method}\n{quote(path, safe='/~')}\n\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
        f"\nhost;x-amz-content-sha256;x-amz-date\n{payload_hash}"
    )
    hashed = hashlib.sha256(canonical.encode()).hexdigest()
    to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{hashed}"
    key = ("AWS4" + secret).encode()
    for part in ("20261028", "us-east-1", "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders=host;x-amz-content-sha256;x-amz-date, "
        f"Signature={signature}"
    )


def test_build_object_key_namespaces_content() -> None:
    assert (
        build_object_key(ObjectNamespace.PDFS, "project-1", "paper.pdf")
        == "pdfs/project-1/paper.pdf"
    )
    assert (
        build_object_key(ObjectNamespace.FIGURES, "project-1", "fig/page-3.png")
        == "figures/project-1/fig/page-3.png"
    )


def test_build_object_key_rejects_traversal_and_bad_segments() -> None:
    with pytest.raises(BizoraError):
        build_object_key(ObjectNamespace.PDFS, "project-1", "../escape.pdf")
    with pytest.raises(BizoraError):
        build_object_key(ObjectNamespace.PDFS, "..", "paper.pdf")
    with pytest.raises(BizoraError):
        build_object_key(ObjectNamespace.PDFS, "project 1", "paper.pdf")
    with pytest.raises(BizoraError):
        build_object_key(
            ObjectNamespace.PDFS, "project-1", "a/b/c/d/e/f/g/h/i.pdf"
        )
    assert build_object_key(
        ObjectNamespace.PDFS, "project-1", "paper.pdf"
    ).split("/")[0] == "pdfs"


def test_object_ref_rejects_traversal_keys() -> None:
    with pytest.raises(ValidationError):
        ObjectRef(bucket="b", key="../escape")
    with pytest.raises(ValidationError):
        ObjectRef(bucket="b", key="/absolute")
    with pytest.raises(ValidationError):
        PresignedDownload(url="ftp://example.test/x", expires_at=FIXED_NOW)


def test_memory_store_round_trip() -> None:
    store = InMemoryObjectStore()
    assert isinstance(store, ObjectStore)

    stored = store.put_object("pdfs/p1/paper.pdf", b"%PDF-fake", "application/pdf")

    assert isinstance(stored, StoredObject)
    assert stored.size_bytes == 9
    assert stored.sha256 == hashlib.sha256(b"%PDF-fake").hexdigest()
    assert store.get_object("pdfs/p1/paper.pdf") == b"%PDF-fake"
    assert store.stat_object("pdfs/p1/paper.pdf") == stored
    assert store.object_exists("pdfs/p1/paper.pdf")


def test_memory_store_missing_key_errors_and_delete_idempotent() -> None:
    store = InMemoryObjectStore()

    with pytest.raises(ObjectNotFoundError):
        store.get_object("pdfs/p1/missing.pdf")
    with pytest.raises(ObjectNotFoundError):
        store.stat_object("pdfs/p1/missing.pdf")
    assert not store.object_exists("pdfs/p1/missing.pdf")

    store.delete_object("pdfs/p1/missing.pdf")
    store.put_object("k", b"v", "text/plain")
    store.delete_object("k")
    assert not store.object_exists("k")


def test_s3_settings_require_full_configuration(monkeypatch: MonkeyPatch) -> None:
    for var in (
        "BIZORA_OBJECT_ENDPOINT",
        "BIZORA_OBJECT_BUCKET",
        "BIZORA_OBJECT_ACCESS_KEY_ID",
        "BIZORA_OBJECT_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    assert not S3Settings.credentials_present()
    with pytest.raises(ConfigurationError):
        S3Settings.from_env()

    monkeypatch.setenv("BIZORA_OBJECT_ENDPOINT", "not-a-url")
    monkeypatch.setenv("BIZORA_OBJECT_BUCKET", "fake-bucket")
    monkeypatch.setenv("BIZORA_OBJECT_ACCESS_KEY_ID", FAKE_KEY)
    monkeypatch.setenv("BIZORA_OBJECT_SECRET_ACCESS_KEY", FAKE_SECRET)
    with pytest.raises(ConfigurationError):
        S3Settings.from_env()


def test_s3_settings_load_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("BIZORA_OBJECT_ENDPOINT", "https://fake-s3.example.test/")
    monkeypatch.setenv("BIZORA_OBJECT_BUCKET", "fake-bucket")
    monkeypatch.setenv("BIZORA_OBJECT_REGION", "us-east-1")
    monkeypatch.setenv("BIZORA_OBJECT_ACCESS_KEY_ID", FAKE_KEY)
    monkeypatch.setenv("BIZORA_OBJECT_SECRET_ACCESS_KEY", FAKE_SECRET)

    assert S3Settings.credentials_present()
    settings = S3Settings.from_env()

    assert settings.endpoint == "https://fake-s3.example.test"
    assert settings.bucket == "fake-bucket"
    assert settings.access_key_id == FAKE_KEY
    assert settings.secret_access_key.get_secret_value() == FAKE_SECRET


def test_sign_v4_headers_match_golden_and_independent() -> None:
    payload_hash = hashlib.sha256(b"hello").hexdigest()
    headers = sign_v4_headers(
        method="PUT",
        url_path="/fake-bucket/pdfs/p1/doc.pdf",
        query_string="",
        host="fake-s3.example.test",
        payload_hash=payload_hash,
        access_key_id="FAKEKEY",
        secret_access_key="FAKESECRET",
        region="us-east-1",
        now=FIXED_NOW,
    )

    assert headers["Authorization"] == GOLDEN_AUTHORIZATION
    assert headers["x-amz-date"] == "20261028T120000Z"
    assert (
        headers["Authorization"]
        == _independent_header_signature(
            method="PUT",
            path="/fake-bucket/pdfs/p1/doc.pdf",
            host="fake-s3.example.test",
            payload_hash=payload_hash,
            access_key="FAKEKEY",
            secret="FAKESECRET",
        )
    )
    assert "FAKESECRET" not in headers["Authorization"]


def test_sign_v4_headers_reject_naive_timestamps() -> None:
    with pytest.raises(ValueError):
        sign_v4_headers(
            method="GET",
            url_path="/b/k",
            query_string="",
            host="h",
            payload_hash="UNSIGNED-PAYLOAD",
            access_key_id=FAKE_KEY,
            secret_access_key=FAKE_SECRET,
            region="us-east-1",
            now=datetime(2026, 10, 28, 12, 0, 0),
        )


def test_presigned_url_structure_and_expiry() -> None:
    download = presigned_get_url(
        endpoint="https://fake-s3.example.test",
        bucket="fake-bucket",
        key="pdfs/p1/doc.pdf",
        access_key_id="FAKEKEY",
        secret_access_key="FAKESECRET",
        region="us-east-1",
        expires_in_seconds=3600,
        now=FIXED_NOW,
    )

    assert isinstance(download, PresignedDownload)
    assert f"X-Amz-Signature={GOLDEN_PRESIGNATURE}" in download.url
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in download.url
    assert "FAKESECRET" not in download.url
    assert download.expires_at == datetime(2026, 10, 28, 13, 0, 0, tzinfo=UTC)

    with pytest.raises(ValueError):
        presigned_get_url(
            endpoint="https://fake-s3.example.test",
            bucket="fake-bucket",
            key="pdfs/p1/doc.pdf",
            access_key_id="FAKEKEY",
            secret_access_key="FAKESECRET",
            region="us-east-1",
            expires_in_seconds=8 * 24 * 3600,
            now=FIXED_NOW,
        )


def _s3_store_with(
    handler: httpx.MockTransport | None,
) -> S3ObjectStore:
    """Build an S3 store whose HTTP layer is the given mock transport."""
    settings = S3Settings(
        endpoint="https://fake-s3.example.test",
        bucket="fake-bucket",
        region="us-east-1",
        access_key_id=FAKE_KEY,
        secret_access_key=SecretStr(FAKE_SECRET),
    )
    store = S3ObjectStore(settings)
    if handler is not None:
        store._client = httpx.Client(transport=handler)
    return store


def test_s3_put_and_get_round_trip_offline() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        seen["url"] = str(request.url)
        if request.method == "PUT":
            return httpx.Response(200)
        return httpx.Response(200, content=b"fake-bytes")

    store = _s3_store_with(httpx.MockTransport(handler))
    try:
        stored = store.put_object("pdfs/p1/doc.pdf", b"fake-bytes", "application/pdf")
        assert stored.sha256 == hashlib.sha256(b"fake-bytes").hexdigest()
        assert store.get_object("pdfs/p1/doc.pdf") == b"fake-bytes"
    finally:
        store.close()

    assert seen["auth"].startswith("AWS4-HMAC-SHA256 Credential=FAKEACCESSKEY/")
    assert FAKE_SECRET not in seen["url"]
    assert FAKE_SECRET not in seen["auth"]


def test_s3_missing_and_failed_requests_map_to_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("missing.pdf"):
            return httpx.Response(404)
        return httpx.Response(500)

    store = _s3_store_with(httpx.MockTransport(handler))
    try:
        with pytest.raises(ObjectNotFoundError):
            store.get_object("pdfs/p1/missing.pdf")
        assert not store.object_exists("pdfs/p1/missing.pdf")
        with pytest.raises(ObjectStorageError) as exc_info:
            store.get_object("pdfs/p1/broken.pdf")
        assert exc_info.value.code == ErrorCode.PROVIDER_REQUEST_FAILED
        store.delete_object("pdfs/p1/missing.pdf")
    finally:
        store.close()


def test_s3_transport_errors_do_not_leak_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("fake connection failure")

    store = _s3_store_with(httpx.MockTransport(handler))
    try:
        with pytest.raises(ObjectStorageError) as exc_info:
            store.get_object("pdfs/p1/doc.pdf")
    finally:
        store.close()
    assert FAKE_SECRET not in str(exc_info.value)
