"""Storage service for handling file uploads and downloads across storage backends.

Two backends are supported:

* ``local`` — files live on the container filesystem under ``UPLOAD_DIR``.
  Used for development and when no object store is configured.
* ``s3``    — files live in an S3-compatible bucket (SeaweedFS here). Selected
  automatically as soon as the ``S3_*`` settings are complete.

Callers should not branch on the backend name directly; use :attr:`is_remote`
when they need to know whether ``get_local_file_path`` handed back a temporary
file that they are responsible for deleting.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, Optional

from app.core.config import settings

if TYPE_CHECKING:
    from botocore.client import BaseClient

logger = logging.getLogger(__name__)

# Objects are streamed to and from the bucket in chunks of this size rather
# than being buffered whole; videos here run to hundreds of megabytes.
STREAM_CHUNK_SIZE = 1024 * 1024


class StorageService:
    """Unified storage service supporting local disk and S3-compatible storage."""

    def __init__(self) -> None:
        """Initialize storage service based on configuration."""
        self.storage_type = settings.STORAGE_TYPE
        self._s3_client: Optional[BaseClient] = None

        if self.storage_type == "s3":
            self._init_s3()

    # Backend capability

    @property
    def is_remote(self) -> bool:
        """True when files live off-box, so local paths are temporary copies."""
        return self.storage_type != "local"

    def _init_s3(self) -> None:
        """Initialize the S3 client used for remote object storage."""
        try:
            import boto3
            from botocore.config import Config
        except ImportError:  # pragma: no cover - dependency is declared
            raise ImportError(
                "boto3 is required for S3 storage. Install it with: pip install boto3"
            ) from None

        try:
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL,
                aws_access_key_id=settings.S3_ACCESS_KEY_ID,
                aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
                region_name=settings.S3_REGION,
                config=Config(
                    # SeaweedFS and MinIO require SigV4 with path-style URLs;
                    # virtual-host style would resolve bucket.host and fail.
                    signature_version="s3v4",
                    s3={"addressing_style": settings.S3_ADDRESSING_STYLE},
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
            logger.info(
                "S3 storage client initialized (endpoint=%s, bucket=%s)",
                settings.S3_ENDPOINT_URL,
                settings.S3_BUCKET,
            )
        except Exception as e:
            logger.error("Failed to initialize S3 client: %s", e)
            raise RuntimeError(f"Failed to initialize S3 client: {e}") from e

    def _get_s3_client(self) -> BaseClient:
        """Return the initialized S3 client, or raise if it is unavailable."""
        if self._s3_client is None:
            raise ValueError(
                "S3 client not initialized. Check the S3_* settings."
            )
        return self._s3_client

    def _validate_file_path(self, file_path: str) -> None:
        """Validate file path to prevent directory traversal attacks.

        Args:
            file_path: Path to validate

        Raises:
            ValueError: If path contains traversal attempts or is invalid
        """
        if not file_path or not file_path.strip():
            raise ValueError("File path cannot be empty")

        # Reject paths containing directory traversal patterns
        if ".." in file_path:
            # For local storage: only allow "../data/" prefix (legitimate relative path structure)
            # Reject all other ".." patterns (security requirement)
            if self.storage_type == "local" and file_path.startswith("../data/"):
                # Allow "../data/..." but check for ".." elsewhere in path (suspicious)
                if ".." in file_path[8:]:  # Check after "../data/"
                    raise ValueError("Invalid file path: path traversal detected")
                # Leading "../data/" is the expected local storage pattern
            else:
                # Object storage or non-data ".." path - reject
                raise ValueError("Invalid file path: path traversal detected")

        # For object storage, reject absolute paths (local storage allows them)
        if self.storage_type != "local" and file_path.startswith("/"):
            raise ValueError(
                "Invalid file path: absolute paths not allowed for object storage"
            )

    def _resolve_local_path(self, file_path: str) -> Path:
        """Resolve local file path (handles absolute or relative paths).

        For absolute paths or paths starting with '..', use them directly.
        For relative paths with prefixes (raw/ or demo/), resolve against UPLOAD_DIR parent.
        For other relative paths, resolve against UPLOAD_DIR.
        """
        path_obj = Path(file_path)
        if path_obj.is_absolute():
            if path_obj.exists():
                return path_obj
            # Docker stores paths as /app/data/videos/raw/... which don't exist
            # on the host. Strip to a relative path the handlers below recognise.
            # Native worker stores host paths like /Users/.../data/videos/raw/...
            # which don't exist inside the Docker API container.
            docker_video_prefix = "/app/data/videos/"
            if file_path.startswith(docker_video_prefix):
                # "/app/data/videos/raw/file.mp4" -> "raw/file.mp4"
                file_path = file_path[len(docker_video_prefix) :]
                path_obj = Path(file_path)
                # Fall through to relative path handling below
            else:
                # Try stripping any host-absolute prefix up to /data/videos/
                # e.g. "/Users/aseda/tennis_coach_app/data/videos/raw/f.mp4" -> "raw/f.mp4"
                marker = "/data/videos/"
                idx = file_path.find(marker)
                if idx != -1:
                    file_path = file_path[idx + len(marker) :]
                    path_obj = Path(file_path)
                    # Fall through to relative path handling below
                else:
                    return path_obj
        # If path starts with '..', it's a relative path to a parent directory
        # Use it as-is (it will be resolved relative to current working directory)
        if file_path.startswith(".."):
            return path_obj.resolve()
        # If path starts with 'raw/' or 'demo/', it's a prefixed path
        # Resolve against UPLOAD_DIR's parent (../data/videos) to avoid double-nesting
        if file_path.startswith("raw/") or file_path.startswith("demo/"):
            return Path(settings.UPLOAD_DIR).parent / file_path
        # For other relative paths, resolve against UPLOAD_DIR
        return Path(settings.UPLOAD_DIR) / file_path

    def upload_file(
        self, file_content: bytes, file_path: str, content_type: Optional[str] = None
    ) -> str:
        """
        Upload a file to storage.

        Args:
            file_content: File content as bytes
            file_path: Path where file should be stored
            content_type: MIME type of the file

        Returns:
            Storage path of the uploaded file (may differ if the name was taken)
        """
        self._validate_file_path(file_path)
        if self.storage_type == "s3":
            return self._upload_to_s3(file_content, file_path, content_type)
        return self._upload_to_local(file_content, file_path)

    def download_file(self, file_path: str) -> bytes:
        """
        Download a file from storage.

        Args:
            file_path: Path to the file in storage

        Returns:
            File content as bytes
        """
        self._validate_file_path(file_path)
        if self.storage_type == "s3":
            return self._download_from_s3(file_path)
        return self._download_from_local(file_path)

    def download_private_file(self, file_path: str) -> bytes:
        """Download a file from the primary bucket or local storage."""
        return self.download_file(file_path)

    def delete_file(self, file_path: str) -> None:
        """
        Delete a file from storage.

        Args:
            file_path: Path to the file in storage
        """
        self._validate_file_path(file_path)
        if self.storage_type == "s3":
            self._delete_from_s3(file_path)
        else:
            self._delete_from_local(file_path)

    def replace_file(
        self,
        old_file_path: str,
        new_file_content: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Replace a file in storage with new content, in place.

        Args:
            old_file_path: Path to the existing file to replace
            new_file_content: New file content as bytes
            content_type: MIME type of the new file

        Returns:
            Storage path of the replaced file (unchanged)
        """
        self._validate_file_path(old_file_path)
        if self.storage_type == "s3":
            # Overwriting the same key is atomic from a reader's point of view,
            # so unlike the old two-step upload/delete there is no window where
            # both the stale and the fresh object exist.
            self._put_s3_object(old_file_path, new_file_content, content_type)
            return old_file_path
        return self._upload_to_local(new_file_content, old_file_path)

    def get_file_url(self, file_path: str) -> str:
        """
        Get a URL to access the file (object storage) or the path (local).

        Args:
            file_path: Path to the file in storage

        Returns:
            Presigned URL for object storage, or the file path for local storage
        """
        return self.create_signed_url(file_path)

    def create_signed_url(self, file_path: str, expires_in: int = 3600) -> str:
        """
        Create a signed URL for secure, time-limited access to a file.

        Note that the app streams video through its own ``/videos/{id}/stream``
        endpoint rather than redirecting browsers here: the object store is on a
        different origin, which would taint the canvas the thumbnail strip draws
        into. This stays available for callers that genuinely want a direct URL.

        Args:
            file_path: Path to the file in storage
            expires_in: Seconds the URL should remain valid (default: 1 hour)

        Returns:
            Signed URL string for object storage, or file path for local storage
        """
        self._validate_file_path(file_path)
        if self.storage_type == "s3":
            return self._create_s3_signed_url(file_path, expires_in)
        return file_path  # Local storage - API route handles serving

    def get_local_file_path(
        self, file_path: str, temp_dir: Optional[str] = None
    ) -> Path:
        """
        Get a local file path for processing.

        For object storage: downloads the file to a temporary location and
        returns that path. For local storage: returns the actual file path.

        IMPORTANT: when :attr:`is_remote` is true the caller MUST delete the
        returned file after processing. Use a try/finally block.

        Args:
            file_path: Path to the file in storage
            temp_dir: Optional directory for temp files (defaults to PROCESSED_DIR)

        Returns:
            Path object pointing to a local file that can be used for processing

        Example:
            temp_path = None
            try:
                temp_path = storage_service.get_local_file_path("raw/video.mp4")
                process_video(temp_path)
            finally:
                if temp_path and storage_service.is_remote:
                    temp_path.unlink(missing_ok=True)
        """
        self._validate_file_path(file_path)

        if self.storage_type == "s3":
            logger.info("Downloading %s from object storage for processing", file_path)

            temp_dir_path = Path(temp_dir) if temp_dir else Path(settings.PROCESSED_DIR)
            temp_dir_path.mkdir(parents=True, exist_ok=True)

            # Stream to disk rather than buffering the whole object in memory:
            # these are full-length videos and the worker container is small.
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=Path(file_path).suffix, dir=str(temp_dir_path)
            ) as temp_file:
                temp_path = Path(temp_file.name)
                self._get_s3_client().download_fileobj(
                    settings.S3_BUCKET, file_path, temp_file
                )

            logger.debug("Downloaded to temp file: %s", temp_path)
            return temp_path

        return self._resolve_local_path(file_path)

    # Object storage methods

    def _put_s3_object(
        self, key: str, file_content: bytes, content_type: Optional[str] = None
    ) -> None:
        """Write an object to the bucket, overwriting any existing key."""
        extra: dict[str, Any] = {}
        if content_type:
            extra["ContentType"] = content_type

        try:
            self._get_s3_client().put_object(
                Bucket=settings.S3_BUCKET, Key=key, Body=file_content, **extra
            )
        except Exception as e:
            logger.error("Failed to upload %s to object storage: %s", key, e)
            raise RuntimeError(f"Failed to upload {key}: {e}") from e

    def object_exists(self, file_path: str) -> bool:
        """Return True when the key is present in the bucket."""
        if self.storage_type != "s3":
            return self._resolve_local_path(file_path).exists()
        try:
            self._get_s3_client().head_object(
                Bucket=settings.S3_BUCKET, Key=file_path
            )
            return True
        except Exception:  # noqa: BLE001 - any failure means "not usable"
            return False

    def _upload_to_s3(
        self, file_content: bytes, file_path: str, content_type: Optional[str] = None
    ) -> str:
        """
        Upload a file to the bucket, generating a unique key if one is taken.

        S3 PUT overwrites silently, so an existing key is probed for first to
        preserve the same no-clobber behaviour local storage has.
        """
        path_obj = Path(file_path)
        directory = str(path_obj.parent) if path_obj.parent != Path(".") else ""
        base_name = path_obj.stem
        extension = path_obj.suffix

        current_path = file_path
        counter = 0
        max_attempts = 1000

        while counter < max_attempts:
            if not self.object_exists(current_path):
                self._put_s3_object(current_path, file_content, content_type)
                if counter > 0:
                    logger.debug(
                        "Key %s already existed, uploaded as %s",
                        file_path,
                        current_path,
                    )
                logger.info("File uploaded to object storage: %s", current_path)
                return current_path

            counter += 1
            if directory:
                current_path = f"{directory}/{base_name}_{counter}{extension}"
            else:
                current_path = f"{base_name}_{counter}{extension}"

        logger.error(
            "Could not generate unique key for %s after %s attempts",
            file_path,
            max_attempts,
        )
        raise RuntimeError(
            f"Could not generate unique key for {file_path} "
            f"after {max_attempts} attempts"
        )

    def _download_from_s3(self, file_path: str) -> bytes:
        """Download an object from the bucket."""
        try:
            response = self._get_s3_client().get_object(
                Bucket=settings.S3_BUCKET, Key=file_path
            )
            return response["Body"].read()
        except Exception as e:
            logger.error("Failed to download %s from object storage: %s", file_path, e)
            raise RuntimeError(f"Failed to download {file_path}: {e}") from e

    def _delete_from_s3(self, file_path: str) -> None:
        """Delete an object from the bucket."""
        try:
            self._get_s3_client().delete_object(
                Bucket=settings.S3_BUCKET, Key=file_path
            )
            logger.info("File deleted from object storage: %s", file_path)
        except Exception as e:
            logger.error("Failed to delete %s from object storage: %s", file_path, e)
            raise RuntimeError(f"Failed to delete {file_path}: {e}") from e

    def _create_s3_signed_url(self, file_path: str, expires_in: int) -> str:
        """Create a presigned GET URL for an object."""
        try:
            return self._get_s3_client().generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.S3_BUCKET, "Key": file_path},
                ExpiresIn=expires_in,
            )
        except Exception as e:
            logger.error("Failed to create signed URL for %s: %s", file_path, e)
            raise RuntimeError(f"Failed to create signed URL: {e}") from e

    def get_object_size(self, file_path: str) -> int:
        """Return the size of a stored file in bytes."""
        self._validate_file_path(file_path)
        if self.storage_type != "s3":
            return self._resolve_local_path(file_path).stat().st_size
        try:
            head = self._get_s3_client().head_object(
                Bucket=settings.S3_BUCKET, Key=file_path
            )
            return int(head["ContentLength"])
        except Exception as e:
            logger.error("Failed to stat %s in object storage: %s", file_path, e)
            raise RuntimeError(f"Failed to stat {file_path}: {e}") from e

    def open_range_stream(
        self, file_path: str, start: Optional[int] = None, end: Optional[int] = None
    ) -> tuple[BinaryIO, int]:
        """Open a byte range of a stored object for streaming.

        Range support is what makes scrubbing work in the browser: the video
        element asks for the slice it needs instead of the whole file.

        Args:
            file_path: Path to the file in storage
            start: First byte of the range, or None for the whole object
            end: Last byte of the range (inclusive), or None for open-ended

        Returns:
            Tuple of (readable body, number of bytes in this response)
        """
        self._validate_file_path(file_path)
        if self.storage_type != "s3":
            raise ValueError("open_range_stream is only supported for object storage")

        params: dict[str, Any] = {"Bucket": settings.S3_BUCKET, "Key": file_path}
        if start is not None:
            params["Range"] = f"bytes={start}-{end if end is not None else ''}"

        try:
            response = self._get_s3_client().get_object(**params)
        except Exception as e:
            logger.error("Failed to open %s from object storage: %s", file_path, e)
            raise RuntimeError(f"Failed to open {file_path}: {e}") from e

        return response["Body"], int(response["ContentLength"])

    # Local storage methods

    def _upload_to_local(self, file_content: bytes, file_path: str) -> str:
        """Upload file to local filesystem."""
        full_path = self._resolve_local_path(file_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, "wb") as f:
            f.write(file_content)

        logger.info("File uploaded to local storage: %s", full_path)
        return str(full_path)

    def _download_from_local(self, file_path: str) -> bytes:
        """Download file from local filesystem."""
        full_path = self._resolve_local_path(file_path)

        with open(full_path, "rb") as f:
            return f.read()

    def _delete_from_local(self, file_path: str) -> None:
        """Delete file from local filesystem."""
        full_path = self._resolve_local_path(file_path)

        if full_path.exists():
            full_path.unlink()
            logger.info("File deleted from local storage: %s", full_path)
        else:
            logger.warning("File not found for deletion: %s", full_path)


# Create singleton instance
storage_service = StorageService()
