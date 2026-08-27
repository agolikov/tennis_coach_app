"""Authentication dependencies for protected routes.

No external identity provider is configured. Both dependencies resolve to the
same local user so route signatures and authorization checks keep working
unchanged; see `settings.auth_required`.
"""

import logging
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# auto_error=False so a missing Authorization header is not itself an error.
security = HTTPBearer(auto_error=False)

LOCAL_USER = {
    "id": "00000000-0000-0000-0000-000000000000",
    "email": "dev@localhost",
    "user_metadata": {},
}


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Return the current user.

    Args:
        request: FastAPI request object
        credentials: Ignored; retained so the security scheme stays documented

    Returns:
        User dict with id, email and user_metadata
    """
    return dict(LOCAL_USER)


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Return the current user for endpoints that also allow anonymous access.

    Args:
        request: FastAPI request object
        credentials: Ignored; retained so the security scheme stays documented

    Returns:
        User dict
    """
    return dict(LOCAL_USER)
