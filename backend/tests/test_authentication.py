"""Tests for the authentication dependencies.

No external identity provider is configured, so both dependencies resolve to
the same local user. These tests pin that contract: routes still receive a
well-formed user dict, and the dependency-override mechanism protected
endpoints rely on still works.
"""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.core.config import settings
from app.dependencies.auth import LOCAL_USER, get_current_user, get_optional_user
from app.main import app

LOCAL_USER_ID = "00000000-0000-0000-0000-000000000000"


class TestAuthDependency:
    """Tests for the authentication dependencies."""

    @pytest.mark.asyncio
    async def test_get_current_user_returns_local_user(self) -> None:
        """Without credentials the local user is returned."""
        result = await get_current_user(request=Mock(), credentials=None)

        assert result["id"] == LOCAL_USER_ID
        assert result["email"] == "dev@localhost"
        assert result["user_metadata"] == {}

    @pytest.mark.asyncio
    async def test_get_current_user_ignores_bearer_token(self) -> None:
        """A supplied token is accepted but carries no identity."""
        credentials = Mock(spec=HTTPAuthorizationCredentials)
        credentials.credentials = "any-token"

        result = await get_current_user(request=Mock(), credentials=credentials)

        assert result["id"] == LOCAL_USER_ID

    @pytest.mark.asyncio
    async def test_get_optional_user_returns_local_user(self) -> None:
        """The optional dependency resolves to the same user."""
        result = await get_optional_user(request=Mock(), credentials=None)

        assert result is not None
        assert result["id"] == LOCAL_USER_ID

    @pytest.mark.asyncio
    async def test_callers_cannot_mutate_shared_user(self) -> None:
        """Each call gets its own dict, so a caller cannot poison the next."""
        first = await get_current_user(request=Mock(), credentials=None)
        first["email"] = "attacker@example.com"

        second = await get_current_user(request=Mock(), credentials=None)

        assert second["email"] == "dev@localhost"
        assert LOCAL_USER["email"] == "dev@localhost"

    def test_auth_is_not_required(self) -> None:
        """No identity provider is wired up, so nothing demands credentials."""
        assert settings.auth_required is False


class TestProtectedEndpoint:
    """Tests for endpoints that depend on the auth dependency."""

    def test_video_upload_rejects_when_dependency_denies(
        self, client: TestClient
    ) -> None:
        """Overriding the dependency still gates the endpoint."""

        async def require_auth() -> None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        app.dependency_overrides[get_current_user] = require_auth
        try:
            response = client.post(
                "/v0/videos/upload",
                files={
                    "file": (
                        "test.mp4",
                        b"\x00\x00\x00\x20ftypmp41\x00\x00\x00\x00mp41isom",
                    )
                },
            )
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()

    def test_video_upload_passes_auth_by_default(self, client: TestClient) -> None:
        """With no override the request gets past auth (validation may still fail)."""
        response = client.post(
            "/v0/videos/upload",
            files={
                "file": (
                    "test.mp4",
                    b"\x00\x00\x00\x20ftypmp41\x00\x00\x00\x00mp41isom",
                )
            },
        )

        assert response.status_code != 401
