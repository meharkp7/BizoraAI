"""S3-compatible object storage over HTTPS with SigV4 request signing.

Works against AWS S3 and S3-compatible services (MinIO, R2, GCSXML)
using path-style URLs and header-based auth; credentials never appear
in URLs, logs, or error messages. Signing helpers are pure functions
so they are unit-testable without any network access.
"""

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode

import httpx
from pydantic import SecretStr

from bizora.contracts.storage import ObjectRef, PresignedDownload, StoredObject
from bizora.core.errors import ConfigurationError
from bizora.storage.base import ObjectNotFoundError, ObjectStorageError

_SERVICE = "s3"
_ALGORITHM = "AWS4-HMAC-SHA256"
_DEFAULT_REGION = "us-east-1"
_MAX_PRESIGN_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True)
class S3Settings:
    """Connection settings for one S3-compatible bucket."""

    endpoint: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: SecretStr

    @staticmethod
    def credentials_present() -> bool:
        """Return whether key material is configured (presence only)."""
        return bool(
            os.environ.get("BIZORA_OBJECT_ACCESS_KEY_ID", "").strip()
            and os.environ.get("BIZORA_OBJECT_SECRET_ACCESS_KEY", "").strip()
        )

    @classmethod
    def from_env(cls) -> "S3Settings":
        """Build settings from environment; fail closed when incomplete."""
        endpoint = os.environ.get("BIZORA_OBJECT_ENDPOINT", "").strip()
        bucket = os.environ.get("BIZORA_OBJECT_BUCKET", "").strip()
        region = os.environ.get("BIZORA_OBJECT_REGION", "").strip() or _DEFAULT_REGION
        access_key = os.environ.get("BIZORA_OBJECT_ACCESS_KEY_ID", "").strip()
        secret = os.environ.get("BIZORA_OBJECT_SECRET_ACCESS_KEY", "").strip()
        if not endpoint:
            raise ConfigurationError("BIZORA_OBJECT_ENDPOINT must be set.")
        if not endpoint.startswith(("https://", "http://")):
            raise ConfigurationError("BIZORA_OBJECT_ENDPOINT must be an HTTP(S) URL.")
        if not bucket:
            raise ConfigurationError("BIZORA_OBJECT_BUCKET must be set.")
        if not access_key or not secret:
            raise ConfigurationError(
                "S3 object storage needs BIZORA_OBJECT_ACCESS_KEY_ID and "
                "BIZORA_OBJECT_SECRET_ACCESS_KEY."
            )
        return cls(
            endpoint=endpoint.rstrip("/"),
            bucket=bucket,
            region=region,
            access_key_id=access_key,
            secret_access_key=SecretStr(secret),
        )


def _hmac_sha256(key: bytes, message: str) -> bytes:
    """Return raw HMAC-SHA256 for one signing step."""
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date_stamp: str, region: str) -> bytes:
    """Derive the SigV4 signing key for one date and region."""
    key_date = _hmac_sha256(f"AWS4{secret}".encode(), date_stamp)
    key_region = _hmac_sha256(key_date, region)
    key_service = _hmac_sha256(key_region, _SERVICE)
    return _hmac_sha256(key_service, "aws4_request")


def _signature(
    *,
    secret: str,
    date_stamp: str,
    region: str,
    string_to_sign: str,
) -> str:
    """Return the hex SigV4 signature for a string-to-sign."""
    return hmac.new(
        _signing_key(secret, date_stamp, region),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def sign_v4_headers(
    *,
    method: str,
    url_path: str,
    query_string: str,
    host: str,
    payload_hash: str,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    now: datetime,
) -> dict[str, str]:
    """Return SigV4 auth headers for one request (pure, offline)."""
    if now.tzinfo is None:
        raise ValueError("Signing timestamps must be timezone-aware.")
    moment = now.astimezone(UTC)
    amz_date = moment.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = moment.strftime("%Y%m%d")
    canonical_uri = quote(url_path, safe="/~")
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_headers = (
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    canonical_request = (
        f"{method}\n{canonical_uri}\n{query_string}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    credential_scope = f"{date_stamp}/{region}/{_SERVICE}/aws4_request"
    hashed_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = (
        f"{_ALGORITHM}\n{amz_date}\n{credential_scope}\n{hashed_request}"
    )
    signature = _signature(
        secret=secret_access_key,
        date_stamp=date_stamp,
        region=region,
        string_to_sign=string_to_sign,
    )
    authorization = (
        f"{_ALGORITHM} Credential={access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": authorization,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }


def presigned_get_url(
    *,
    endpoint: str,
    bucket: str,
    key: str,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    expires_in_seconds: int,
    now: datetime,
) -> PresignedDownload:
    """Build a presigned GET URL for one key (pure, offline)."""
    if now.tzinfo is None:
        raise ValueError("Signing timestamps must be timezone-aware.")
    if not 1 <= expires_in_seconds <= _MAX_PRESIGN_SECONDS:
        raise ValueError("Presigned expiry must be within 1 second and 7 days.")
    ObjectRef(bucket=bucket, key=key)
    moment = now.astimezone(UTC)
    amz_date = moment.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = moment.strftime("%Y%m%d")
    credential_scope = f"{date_stamp}/{region}/{_SERVICE}/aws4_request"
    params = {
        "X-Amz-Algorithm": _ALGORITHM,
        "X-Amz-Credential": f"{access_key_id}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires_in_seconds),
        "X-Amz-SignedHeaders": "host",
    }
    path = f"/{bucket}/{key}"
    host = endpoint.split("://", 1)[1]
    canonical_query = urlencode(sorted(params.items()))
    canonical_request = (
        f"GET\n{quote(path, safe='/~')}\n{canonical_query}\n"
        f"host:{host}\n\nhost\nUNSIGNED-PAYLOAD"
    )
    hashed_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = (
        f"{_ALGORITHM}\n{amz_date}\n{credential_scope}\n{hashed_request}"
    )
    signature = _signature(
        secret=secret_access_key,
        date_stamp=date_stamp,
        region=region,
        string_to_sign=string_to_sign,
    )
    url = f"{endpoint}{path}?{canonical_query}&X-Amz-Signature={signature}"
    return PresignedDownload(
        url=url,
        expires_at=moment + timedelta(seconds=expires_in_seconds),
    )


class S3ObjectStore:
    """S3-compatible backend using path-style URLs and SigV4 headers."""

    def __init__(self, settings: S3Settings, timeout_seconds: float = 30.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self._settings = settings
        self._host = settings.endpoint.split("://", 1)[1]
        self._client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()

    def _object_url(self, key: str) -> str:
        """Return the path-style URL for one key."""
        ObjectRef(bucket=self._settings.bucket, key=key)
        return f"{self._settings.endpoint}/{self._settings.bucket}/{key}"

    def _auth_headers(
        self, method: str, key: str, payload_hash: str
    ) -> dict[str, str]:
        """Return SigV4 headers for one request."""
        return sign_v4_headers(
            method=method,
            url_path=f"/{self._settings.bucket}/{key}",
            query_string="",
            host=self._host,
            payload_hash=payload_hash,
            access_key_id=self._settings.access_key_id,
            secret_access_key=self._settings.secret_access_key.get_secret_value(),
            region=self._settings.region,
            now=datetime.now(UTC),
        )

    def _send(
        self,
        method: str,
        key: str,
        payload: bytes,
        content_type: str | None,
    ) -> httpx.Response:
        """Send one signed request, translating transport errors."""
        payload_hash = hashlib.sha256(payload).hexdigest()
        headers = self._auth_headers(method, key, payload_hash)
        if content_type is not None:
            headers["Content-Type"] = content_type
        try:
            return self._client.request(
                method, self._object_url(key), content=payload, headers=headers
            )
        except httpx.HTTPError as exc:
            raise ObjectStorageError(
                f"S3 {method} request failed for key '{key}': {exc.__class__.__name__}."
            ) from exc

    def put_object(
        self, key: str, data: bytes, content_type: str
    ) -> StoredObject:
        """Store bytes at a key, overwriting any previous value."""
        response = self._send("PUT", key, bytes(data), content_type)
        if response.status_code not in (200, 204):
            raise ObjectStorageError(
                f"S3 PUT failed for key '{key}' "
                f"with status {response.status_code}."
            )
        return StoredObject(
            bucket=self._settings.bucket,
            key=key,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            content_type=content_type,
        )

    def get_object(self, key: str) -> bytes:
        """Return an object's bytes or raise ObjectNotFoundError."""
        response = self._send("GET", key, b"", None)
        if response.status_code == 404:
            raise ObjectNotFoundError(f"Object '{key}' does not exist.")
        if response.status_code != 200:
            raise ObjectStorageError(
                f"S3 GET failed for key '{key}' "
                f"with status {response.status_code}."
            )
        return bytes(response.content)

    def stat_object(self, key: str) -> StoredObject:
        """Return metadata via GET (S3 HEAD cannot yield a SHA-256)."""
        response = self._send("GET", key, b"", None)
        if response.status_code == 404:
            raise ObjectNotFoundError(f"Object '{key}' does not exist.")
        if response.status_code != 200:
            raise ObjectStorageError(
                f"S3 GET failed for key '{key}' "
                f"with status {response.status_code}."
            )
        content_type = response.headers.get("content-type", "application/octet-stream")
        return StoredObject(
            bucket=self._settings.bucket,
            key=key,
            size_bytes=len(response.content),
            sha256=hashlib.sha256(response.content).hexdigest(),
            content_type=content_type,
        )

    def delete_object(self, key: str) -> None:
        """Remove an object; missing keys are a silent no-op."""
        response = self._send("DELETE", key, b"", None)
        if response.status_code not in (200, 204, 404):
            raise ObjectStorageError(
                f"S3 DELETE failed for key '{key}' "
                f"with status {response.status_code}."
            )

    def object_exists(self, key: str) -> bool:
        """Return whether an object exists at a key."""
        response = self._send("HEAD", key, b"", None)
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        raise ObjectStorageError(
            f"S3 HEAD failed for key '{key}' "
            f"with status {response.status_code}."
        )

    def presigned_download(
        self, key: str, expires_in_seconds: int = 3600
    ) -> PresignedDownload:
        """Return a time-limited direct-download URL without network I/O."""
        return presigned_get_url(
            endpoint=self._settings.endpoint,
            bucket=self._settings.bucket,
            key=key,
            access_key_id=self._settings.access_key_id,
            secret_access_key=self._settings.secret_access_key.get_secret_value(),
            region=self._settings.region,
            expires_in_seconds=expires_in_seconds,
            now=datetime.now(UTC),
        )
