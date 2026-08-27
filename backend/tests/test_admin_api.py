"""
Tests for admin API endpoints and authorization.

TDD Contract: Tests define behavior, not implementation details.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.dependencies.auth import get_current_user
from app.main import app
from app.utils.authorization import is_admin, require_admin


class TestAdminAuthorization:
    """Tests for admin authorization utilities."""

    def test_is_admin_with_valid_admin_id(self) -> None:
        """Test is_admin returns True for user in admin allowlist."""
        admin_user_id = settings.admin_user_ids[0]
        user = {
            "id": admin_user_id,
            "email": "admin@example.com",
            "user_metadata": {},
        }

        assert is_admin(user) is True

    def test_is_admin_with_non_admin_id(self) -> None:
        """Test is_admin returns False for user not in admin allowlist."""
        user = {
            "id": "11111111-1111-1111-1111-111111111111",
            "email": "user@example.com",
            "user_metadata": {},
        }

        assert is_admin(user) is False

    def test_is_admin_with_missing_id(self) -> None:
        """Test is_admin returns False when user dict has no id."""
        user = {
            "email": "user@example.com",
            "user_metadata": {},
        }

        assert is_admin(user) is False

    def test_is_admin_with_empty_id(self) -> None:
        """Test is_admin returns False when user id is empty string."""
        user = {
            "id": "",
            "email": "user@example.com",
            "user_metadata": {},
        }

        assert is_admin(user) is False

    def test_is_admin_with_multiple_admin_ids(self) -> None:
        """Test is_admin works with comma-separated admin IDs."""
        with patch.object(settings, "ADMIN_USER_IDS", "admin1,admin2,admin3"):
            user1 = {"id": "admin1", "email": "admin1@example.com"}
            user2 = {"id": "admin2", "email": "admin2@example.com"}
            user3 = {"id": "admin3", "email": "admin3@example.com"}
            non_admin = {"id": "user1", "email": "user@example.com"}

            assert is_admin(user1) is True
            assert is_admin(user2) is True
            assert is_admin(user3) is True
            assert is_admin(non_admin) is False

    def test_require_admin_allows_admin(self) -> None:
        """Test require_admin does not raise for admin user."""
        admin_user_id = settings.admin_user_ids[0]
        user = {
            "id": admin_user_id,
            "email": "admin@example.com",
            "user_metadata": {},
        }

        # Should not raise
        require_admin(user)

    def test_require_admin_raises_for_non_admin(self) -> None:
        """Test require_admin raises 403 for non-admin user."""
        user = {
            "id": "11111111-1111-1111-1111-111111111111",
            "email": "user@example.com",
            "user_metadata": {},
        }

        with pytest.raises(HTTPException) as exc_info:
            require_admin(user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Admin access required" in str(exc_info.value.detail)


class TestAdminStatusEndpoint:
    """Tests for GET /admin/status endpoint."""

    @patch("app.api.routes.admin.is_admin", return_value=True)
    def test_admin_status_as_admin(self, mock_is_admin, client: TestClient) -> None:
        """Test admin status endpoint returns True for admin user."""
        response = client.get("/v0/admin/status")

        assert response.status_code == 200
        data = response.json()
        assert data["is_admin"] is True

    def test_admin_status_as_non_admin(self, client: TestClient) -> None:
        """Test admin status endpoint returns False for non-admin user."""

        async def mock_non_admin() -> dict:
            return {
                "id": "11111111-1111-1111-1111-111111111111",
                "email": "user@example.com",
                "user_metadata": {},
            }

        app.dependency_overrides[get_current_user] = mock_non_admin

        try:
            response = client.get("/v0/admin/status")

            assert response.status_code == 200
            data = response.json()
            assert data["is_admin"] is False
        finally:
            app.dependency_overrides.clear()

    def test_admin_status_requires_auth(self, client: TestClient) -> None:
        """Test admin status endpoint requires authentication."""

        async def require_auth() -> None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        app.dependency_overrides[get_current_user] = require_auth

        try:
            response = client.get("/v0/admin/status")

            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


class TestUploadForUserEndpoint:
    """Tests for POST /admin/videos/upload-for-user endpoint."""

    def test_upload_for_user_requires_admin(self, client: TestClient) -> None:
        """Test upload-for-user endpoint requires admin access."""

        async def mock_non_admin() -> dict:
            return {
                "id": "11111111-1111-1111-1111-111111111111",
                "email": "user@example.com",
                "user_metadata": {},
            }

        app.dependency_overrides[get_current_user] = mock_non_admin

        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_file:
                tmp_file.write(
                    b"\x00\x00\x00\x20ftypmp41\x00\x00\x00\x00mp41isom"
                    + b"\x00" * 10000
                )
                tmp_file_path = tmp_file.name

            try:
                with open(tmp_file_path, "rb") as f:
                    response = client.post(
                        "/v0/admin/videos/upload-for-user",
                        files={"file": ("test.mp4", f, "video/mp4")},
                        params={
                            "target_user_id": "22222222-2222-2222-2222-222222222222"
                        },
                    )

                assert response.status_code == 403
                error_data = response.json()
                assert "error" in error_data or "Admin access required" in str(
                    response.text
                )
            finally:
                Path(tmp_file_path).unlink(missing_ok=True)
        finally:
            app.dependency_overrides.clear()

    def test_upload_for_user_validates_target_user_id(self, client: TestClient) -> None:
        """Test upload-for-user validates target_user_id parameter."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_file:
            tmp_file.write(
                b"\x00\x00\x00\x20ftypmp41\x00\x00\x00\x00mp41isom" + b"\x00" * 10000
            )
            tmp_file_path = tmp_file.name

        try:
            with open(tmp_file_path, "rb") as f:
                response = client.post(
                    "/v0/admin/videos/upload-for-user",
                    files={"file": ("test.mp4", f, "video/mp4")},
                    params={"target_user_id": "invalid-user-id"},
                )

            assert response.status_code == 400
        finally:
            Path(tmp_file_path).unlink(missing_ok=True)

    def test_upload_for_user_success(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Test successful upload-for-user assigns video to target user."""
        target_user_id = "22222222-2222-2222-2222-222222222222"

        with (
            patch("app.services.storage_service.storage_service") as mock_storage,
            patch.object(settings, "AUTO_ENQUEUE_ON_UPLOAD", False),
            patch.object(settings, "TRANSCODE_ENABLED", False),
        ):
            # Mock storage
            mock_storage.upload_file.return_value = "storage/path/test.mp4"

            # Create test video file
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_file:
                tmp_file.write(
                    b"\x00\x00\x00\x20ftypmp41\x00\x00\x00\x00mp41isom"
                    + b"\x00" * 10000
                )
                tmp_file_path = tmp_file.name

            try:
                with open(tmp_file_path, "rb") as f:
                    response = client.post(
                        "/v0/admin/videos/upload-for-user",
                        files={"file": ("test.mp4", f, "video/mp4")},
                        params={"target_user_id": target_user_id},
                    )

                assert response.status_code == 200
                data = response.json()
                assert "video_id" in data
                assert "filename" in data

                # Verify video was created with target user_id
                from app.models.video import Video

                video = (
                    db_session.query(Video).filter(Video.id == data["video_id"]).first()
                )
                assert video is not None
                assert video.user_id == target_user_id
                # Admin user should NOT be the owner
                assert video.user_id != "00000000-0000-0000-0000-000000000000"
            finally:
                Path(tmp_file_path).unlink(missing_ok=True)


class TestDemoManagementEndpoints:
    """Tests for demo management endpoints (admin only)."""

    def test_list_demos_requires_admin(self, client: TestClient) -> None:
        """Test list demos endpoint requires admin access."""

        async def mock_non_admin() -> dict:
            return {
                "id": "11111111-1111-1111-1111-111111111111",
                "email": "user@example.com",
                "user_metadata": {},
            }

        app.dependency_overrides[get_current_user] = mock_non_admin

        try:
            response = client.get("/v0/admin/demos")

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_list_demos_success(self, client: TestClient, db_session: Session) -> None:
        """Test list demos returns demo videos for admin."""
        from app.services import video_service

        # Create a demo video
        demo_video = video_service.create_video_record(
            db=db_session,
            filename="demo.mp4",
            file_path="storage/demo.mp4",
            file_size=1024,
            user_id=settings.DEMO_USER_ID,
            content_type="video/mp4",
            duration=1.0,
            fps=30.0,
            width=640,
            height=480,
            frame_count=30,
            is_demo=True,
        )

        try:
            response = client.get("/v0/admin/demos")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            demo_ids = [item["id"] for item in data]
            assert demo_video.id in demo_ids
            # Verify response shape includes job_status
            item = next(d for d in data if d["id"] == demo_video.id)
            assert "job_status" in item
            assert item["job_status"] is None  # no active jobs for new video
        finally:
            db_session.delete(demo_video)
            db_session.commit()

    def test_set_active_demo_requires_admin(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Test set active demo endpoint requires admin access."""
        from app.services import video_service

        # Create a demo video
        demo_video = video_service.create_video_record(
            db=db_session,
            filename="demo.mp4",
            file_path="storage/demo.mp4",
            file_size=1024,
            user_id=settings.DEMO_USER_ID,
            content_type="video/mp4",
            duration=1.0,
            fps=30.0,
            width=640,
            height=480,
            frame_count=30,
            is_demo=True,
        )

        async def mock_non_admin() -> dict:
            return {
                "id": "11111111-1111-1111-1111-111111111111",
                "email": "user@example.com",
                "user_metadata": {},
            }

        app.dependency_overrides[get_current_user] = mock_non_admin

        try:
            response = client.post(f"/v0/admin/demos/{demo_video.id}/set-active")

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()
            db_session.delete(demo_video)
            db_session.commit()

    def test_analyze_demo_pose_requires_admin(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Test analyze demo pose endpoint requires admin access."""
        from app.services import video_service

        # Create a demo video
        demo_video = video_service.create_video_record(
            db=db_session,
            filename="demo.mp4",
            file_path="storage/demo.mp4",
            file_size=1024,
            user_id=settings.DEMO_USER_ID,
            content_type="video/mp4",
            duration=1.0,
            fps=30.0,
            width=640,
            height=480,
            frame_count=30,
            is_demo=True,
        )

        async def mock_non_admin() -> dict:
            return {
                "id": "11111111-1111-1111-1111-111111111111",
                "email": "user@example.com",
                "user_metadata": {},
            }

        app.dependency_overrides[get_current_user] = mock_non_admin

        try:
            response = client.post(f"/v0/admin/demos/{demo_video.id}/analyze-pose")

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()
            db_session.delete(demo_video)
            db_session.commit()


class TestUploadForUserValidation:
    """The target user id is validated by shape now that there is no directory."""

    def test_rejects_non_uuid_target_user(self, client: TestClient) -> None:
        """A malformed target user id is refused rather than silently accepted."""
        response = client.post(
            "/v0/admin/videos/upload-for-user",
            params={"target_user_id": "not-a-uuid"},
            files={
                "file": (
                    "test.mp4",
                    b"\x00\x00\x00\x20ftypmp41\x00\x00\x00\x00mp41isom",
                )
            },
        )

        assert response.status_code != 200
