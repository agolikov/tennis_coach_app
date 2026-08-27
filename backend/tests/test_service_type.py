import asyncio
from unittest.mock import patch

from app.main import app, lifespan


def test_api_only_service_type_skips_embedded_worker() -> None:
    async def run_lifespan() -> None:
        with (
            patch("app.main.create_tables_if_not_exists"),
            patch("app.main.os.getenv", return_value="api-only"),
            patch("app.main.start_rq_worker") as start_rq_worker,
        ):
            async with lifespan(app):
                pass

        start_rq_worker.assert_not_called()

    asyncio.run(run_lifespan())
