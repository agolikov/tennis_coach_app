"""Tests for storage service."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from app.core.config import settings
from app.services.storage_service import StorageService


class TestStorageServiceLocal:
    """Test local storage operations."""

    def test_upload_to_local(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test uploading file to local filesystem."""
        # Override UPLOAD_DIR for this test
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()
            file_path = "test_video.mp4"

            result_path = service.upload_file(sample_video_content, file_path)

            # Verify file was created
            full_path = temp_upload_dir / file_path
            assert full_path.exists()
            assert full_path.read_bytes() == sample_video_content
            assert result_path == str(full_path)

    def test_download_from_local(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test downloading file from local storage."""
        # Create a file first
        file_path = "test_video.mp4"
        full_path = temp_upload_dir / file_path
        full_path.write_bytes(sample_video_content)

        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()
            downloaded_content = service.download_file(file_path)

            assert downloaded_content == sample_video_content

    def test_delete_from_local(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test deleting file from local storage."""
        # Create a file first
        file_path = "test_video.mp4"
        full_path = temp_upload_dir / file_path
        full_path.write_bytes(sample_video_content)
        assert full_path.exists()

        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()
            service.delete_file(file_path)

            assert not full_path.exists()

    def test_get_file_url_local(self) -> None:
        """Test getting file URL for local storage."""
        with patch.object(settings, "PROFILE", "local"):
            service = StorageService()
            file_path = "test_video.mp4"

            result = service.get_file_url(file_path)

            # Local storage returns the path as-is
            assert result == file_path

    def test_upload_local_creates_directories(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test that upload creates parent directories if missing."""
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()
            file_path = "subdir/nested/test_video.mp4"

            result_path = service.upload_file(sample_video_content, file_path)

            # Verify nested directories were created
            full_path = temp_upload_dir / file_path
            assert full_path.exists()
            assert full_path.parent.exists()
            assert full_path.parent.parent.exists()
            assert result_path == str(full_path)

    def test_resolve_local_path_absolute(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test that absolute paths are handled correctly."""
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()
            absolute_path = str(temp_upload_dir / "absolute_video.mp4")

            result_path = service.upload_file(sample_video_content, absolute_path)

            # Should use absolute path as-is
            assert result_path == absolute_path
            assert Path(absolute_path).exists()

    def test_resolve_local_path_relative(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test that relative paths are resolved correctly."""
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()
            relative_path = "relative_video.mp4"

            result_path = service.upload_file(sample_video_content, relative_path)

            # Should resolve relative to UPLOAD_DIR
            expected_path = temp_upload_dir / relative_path
            assert result_path == str(expected_path)
            assert expected_path.exists()

    def test_download_local_file_not_found(self, temp_upload_dir: Path) -> None:
        """Test that downloading non-existent file raises error."""
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()

            with pytest.raises(FileNotFoundError):
                service.download_file("nonexistent.mp4")

    def test_delete_local_file_not_found(self, temp_upload_dir: Path) -> None:
        """Test that deleting non-existent file logs warning but doesn't raise."""
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()

            # Should not raise, just log warning
            service.delete_file("nonexistent.mp4")


class TestStorageServiceInitialization:
    """Test storage service initialization."""


class TestStorageServicePathValidation:
    """Test path validation in storage service."""

    def test_validate_file_path_rejects_traversal(self) -> None:
        """Test that path traversal attempts are rejected."""
        with patch.object(settings, "PROFILE", "local"):
            service = StorageService()

            with pytest.raises(ValueError) as exc_info:
                service.upload_file(b"content", "../../etc/passwd")

            assert "path traversal detected" in str(exc_info.value)


    def test_validate_file_path_allows_absolute_paths_for_local(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test that absolute paths are allowed for local storage."""
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()
            absolute_path = str(temp_upload_dir / "absolute_file.mp4")

            # Should not raise for local storage
            service.upload_file(sample_video_content, absolute_path)
            assert Path(absolute_path).exists()

    def test_validate_file_path_rejects_empty_path(self) -> None:
        """Test that empty paths are rejected."""
        with patch.object(settings, "PROFILE", "local"):
            service = StorageService()

            with pytest.raises(ValueError) as exc_info:
                service.upload_file(b"content", "")

            assert "File path cannot be empty" in str(exc_info.value)

    def test_validate_file_path_allows_safe_relative_paths(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test that safe relative paths are allowed."""
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()

            # Should not raise
            service.upload_file(sample_video_content, "safe_file.mp4")
            assert (temp_upload_dir / "safe_file.mp4").exists()


class TestStorageServiceErrorHandling:
    """Test error handling in storage service."""


class TestStorageServiceIntegration:
    """Integration tests for storage service."""

    def test_upload_download_roundtrip_local(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test upload then download returns same content."""
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()
            file_path = "test_video.mp4"

            # Upload
            upload_result = service.upload_file(sample_video_content, file_path)
            assert upload_result == str(temp_upload_dir / file_path)

            # Download
            downloaded = service.download_file(file_path)
            assert downloaded == sample_video_content

    def test_upload_delete_roundtrip_local(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test upload then delete removes file."""
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()
            file_path = "test_video.mp4"
            full_path = temp_upload_dir / file_path

            # Upload
            service.upload_file(sample_video_content, file_path)
            assert full_path.exists()

            # Delete
            service.delete_file(file_path)
            assert not full_path.exists()


class TestStorageServiceTypeSwitching:
    """Test storage type switching."""

    def test_storage_type_local(self) -> None:
        """Test service uses local storage when STORAGE_TYPE=local."""
        with patch.object(settings, "PROFILE", "local"):
            service = StorageService()

            assert service.storage_type == "local"
            # Should return path for local storage
            assert service.get_file_url("test.mp4") == "test.mp4"


class TestStorageServiceReplaceFile:
    """Test replace_file method."""

    def test_replace_file_overwrites_content(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test that replace_file overwrites existing file with new content."""
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()
            file_path = "test_video.mp4"
            full_path = temp_upload_dir / file_path

            # Create initial file
            initial_content = b"initial content"
            service.upload_file(initial_content, file_path)
            assert full_path.exists()
            assert full_path.read_bytes() == initial_content

            # Replace with new content
            new_content = sample_video_content
            result_path = service.replace_file(file_path, new_content)

            # Verify file exists at same path with new content
            assert result_path == str(full_path)
            assert full_path.exists()
            assert full_path.read_bytes() == new_content

    def test_replace_file_validates_path(
        self, temp_upload_dir: Path, sample_video_content: bytes
    ) -> None:
        """Test that replace_file validates path and rejects traversal attempts."""
        with (
            patch.object(settings, "UPLOAD_DIR", str(temp_upload_dir)),
            patch.object(settings, "PROFILE", "local"),
        ):
            service = StorageService()

            with pytest.raises(ValueError, match="path traversal detected"):
                service.replace_file("../etc/passwd", sample_video_content)



S3_SETTINGS = {
    "S3_ENDPOINT_URL": "http://storage.invalid:8333",
    "S3_BUCKET": "test-bucket",
    "S3_ACCESS_KEY_ID": "test-key",
    "S3_SECRET_ACCESS_KEY": "test-secret",
    "S3_REGION": "us-east-1",
    "S3_ADDRESSING_STYLE": "path",
}


@pytest.fixture
def s3_service() -> Any:
    """A StorageService in S3 mode with its boto3 client mocked out."""
    mock_client = Mock()
    with (
        patch.multiple(settings, **S3_SETTINGS),
        patch("boto3.client", return_value=mock_client) as mock_factory,
    ):
        service = StorageService()
        service._mock_client = mock_client
        service._mock_factory = mock_factory
        yield service


class TestStorageServiceS3:
    """Test object storage operations (mocked boto3)."""

    def test_storage_type_is_s3_when_configured(self) -> None:
        """Complete S3 settings select the object-storage backend."""
        with patch.multiple(settings, **S3_SETTINGS):
            assert settings.s3_configured is True
            assert settings.storage_type == "s3"
            assert settings.STORAGE_TYPE == "s3"

    def test_storage_type_falls_back_to_local(self) -> None:
        """With no bucket configured the service stays on local disk."""
        with patch.object(settings, "S3_BUCKET", None):
            assert settings.s3_configured is False
            assert settings.storage_type == "local"

    def test_is_remote(self, s3_service: Any) -> None:
        """S3 is remote; local is not."""
        assert s3_service.is_remote is True
        with patch.object(settings, "S3_BUCKET", None):
            assert StorageService().is_remote is False

    def test_client_uses_sigv4_and_path_style(self, s3_service: Any) -> None:
        """SeaweedFS needs SigV4 with path-style addressing to authenticate."""
        _, kwargs = s3_service._mock_factory.call_args
        assert kwargs["endpoint_url"] == S3_SETTINGS["S3_ENDPOINT_URL"]
        assert kwargs["region_name"] == "us-east-1"
        config = kwargs["config"]
        assert config.signature_version == "s3v4"
        assert config.s3["addressing_style"] == "path"

    def test_upload_puts_object(self, s3_service: Any) -> None:
        """A free key is written straight through, unchanged."""
        s3_service._mock_client.head_object.side_effect = Exception("404")

        result = s3_service.upload_file(b"data", "raw/clip.mp4", "video/mp4")

        assert result == "raw/clip.mp4"
        _, kwargs = s3_service._mock_client.put_object.call_args
        assert kwargs["Bucket"] == "test-bucket"
        assert kwargs["Key"] == "raw/clip.mp4"
        assert kwargs["Body"] == b"data"
        assert kwargs["ContentType"] == "video/mp4"

    def test_upload_does_not_clobber_existing_key(self, s3_service: Any) -> None:
        """An existing key gets a counter suffix instead of being overwritten."""
        # First probe finds a file, second finds nothing.
        s3_service._mock_client.head_object.side_effect = [
            {"ContentLength": 1},
            Exception("404"),
        ]

        result = s3_service.upload_file(b"data", "raw/clip.mp4")

        assert result == "raw/clip_1.mp4"
        assert s3_service._mock_client.put_object.call_args[1]["Key"] == "raw/clip_1.mp4"

    def test_download_reads_body(self, s3_service: Any) -> None:
        """Download returns the object's bytes."""
        body = Mock()
        body.read.return_value = b"video-bytes"
        s3_service._mock_client.get_object.return_value = {"Body": body}

        assert s3_service.download_file("raw/clip.mp4") == b"video-bytes"

    def test_delete_removes_object(self, s3_service: Any) -> None:
        """Delete targets the exact key in the configured bucket."""
        s3_service.delete_file("raw/clip.mp4")

        s3_service._mock_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="raw/clip.mp4"
        )

    def test_replace_file_overwrites_in_place(self, s3_service: Any) -> None:
        """Replace keeps the same key, so no stale object is left behind."""
        result = s3_service.replace_file("raw/clip.mp4", b"new", "video/mp4")

        assert result == "raw/clip.mp4"
        assert s3_service._mock_client.put_object.call_args[1]["Key"] == "raw/clip.mp4"
        s3_service._mock_client.delete_object.assert_not_called()

    def test_create_signed_url(self, s3_service: Any) -> None:
        """Presigned URLs are generated for the requested key and lifetime."""
        s3_service._mock_client.generate_presigned_url.return_value = "http://signed"

        assert s3_service.create_signed_url("raw/clip.mp4", 600) == "http://signed"
        _, kwargs = s3_service._mock_client.generate_presigned_url.call_args
        assert kwargs["Params"] == {"Bucket": "test-bucket", "Key": "raw/clip.mp4"}
        assert kwargs["ExpiresIn"] == 600

    def test_get_object_size(self, s3_service: Any) -> None:
        """Size comes from the object's ContentLength."""
        s3_service._mock_client.head_object.return_value = {"ContentLength": 4096}

        assert s3_service.get_object_size("raw/clip.mp4") == 4096

    def test_open_range_stream_sends_range_header(self, s3_service: Any) -> None:
        """A bounded range becomes an S3 Range header, which is what enables seeking."""
        body = Mock()
        s3_service._mock_client.get_object.return_value = {
            "Body": body,
            "ContentLength": 100,
        }

        stream, length = s3_service.open_range_stream("raw/clip.mp4", 0, 99)

        assert stream is body
        assert length == 100
        assert s3_service._mock_client.get_object.call_args[1]["Range"] == "bytes=0-99"

    def test_open_range_stream_open_ended(self, s3_service: Any) -> None:
        """An open-ended range omits the upper bound."""
        s3_service._mock_client.get_object.return_value = {
            "Body": Mock(),
            "ContentLength": 50,
        }

        s3_service.open_range_stream("raw/clip.mp4", 50, None)

        assert s3_service._mock_client.get_object.call_args[1]["Range"] == "bytes=50-"

    def test_open_range_stream_whole_object(self, s3_service: Any) -> None:
        """No start means no Range header at all."""
        s3_service._mock_client.get_object.return_value = {
            "Body": Mock(),
            "ContentLength": 10,
        }

        s3_service.open_range_stream("raw/clip.mp4")

        assert "Range" not in s3_service._mock_client.get_object.call_args[1]

    def test_object_exists(self, s3_service: Any) -> None:
        """head_object success means present, failure means absent."""
        s3_service._mock_client.head_object.return_value = {"ContentLength": 1}
        assert s3_service.object_exists("raw/clip.mp4") is True

        s3_service._mock_client.head_object.side_effect = Exception("404")
        assert s3_service.object_exists("raw/missing.mp4") is False

    def test_rejects_absolute_paths(self, s3_service: Any) -> None:
        """Absolute paths are not valid object keys."""
        with pytest.raises(ValueError, match="absolute paths not allowed"):
            s3_service.upload_file(b"x", "/etc/passwd")

    def test_rejects_path_traversal(self, s3_service: Any) -> None:
        """Traversal sequences are rejected for object storage."""
        with pytest.raises(ValueError, match="path traversal"):
            s3_service.upload_file(b"x", "../../secret.mp4")

    def test_upload_failure_raises_runtime_error(self, s3_service: Any) -> None:
        """A storage failure surfaces as RuntimeError, not a boto3 error."""
        s3_service._mock_client.head_object.side_effect = Exception("404")
        s3_service._mock_client.put_object.side_effect = Exception("boom")

        with pytest.raises(RuntimeError, match="Failed to upload"):
            s3_service.upload_file(b"x", "raw/clip.mp4")
