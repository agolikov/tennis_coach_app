# S²Serve — Backend

Technical guide for contributors working in `backend/`.

For product context and a project intro, see the root [`README.md`](../README.md).

This service handles:

- Video upload and metadata persistence
- Serve window tagging and biomechanics analysis
- Background jobs for video transcode and pose processing (MediaPipe)
- REST API under `/v0/`

## Quick start (Docker, preferred)

From the repo root:

```bash
docker compose up --build
```

This starts everything: API (`localhost:8000`), RQ worker, PostgreSQL, Redis, and the RQ dashboard (`localhost:9181`). No `.env` setup needed for local development — `PROFILE=local` is the default, which bypasses authentication and uses local disk storage.

Check it is working:

```bash
curl http://localhost:8000/health
open http://localhost:8000/docs  # Swagger UI
```

## Running tests (Docker)

Always use the container when testing, so you get the same environment as CI:

```bash
docker compose exec backend pytest
docker compose exec backend pytest tests/test_video_api.py  # specific file
docker compose exec backend pytest -k "test_upload"         # filter by name
```

## Local dev without Docker

For contributors who need faster iteration or want to run the backend directly (e.g. to attach a debugger or run a single service).

**Prerequisites:** Python 3.11+, FFmpeg, and a running PostgreSQL and Redis instance (easiest: `docker compose up -d postgres redis`).

```bash
# Install deps (uses uv, not pip)
cd backend
uv sync --extra dev

# Minimal .env for local dev
cat > .env <<'EOF'
PROFILE=local
DATABASE_URL=postgresql://tennis:tennis_dev@localhost:5432/tennis_coach
REDIS_URL=redis://localhost:6379/0
EOF

# Run the API
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run the worker (separate terminal)
python -m rq worker --with-scheduler
```

The API runs as a fixed local user. With no `S3_*` variables set it stores files on local disk, so no object-storage credentials are needed.

## Environment variables

### Local development

The Docker Compose setup provides all of these automatically. If running bare:

| Variable | Default | Notes |
|---|---|---|
| `PROFILE` | `local` | Selects processing limits |
| `DATABASE_URL` | Docker default | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | RQ broker |
| `UPLOAD_DIR` | `./data/videos/raw` | Where uploaded videos are stored |
| `PROCESSED_DIR` | `./data/videos/processed` | Transcoding scratch space |

### Object storage

Set all four of these to keep video data in an S3-compatible bucket (SeaweedFS,
MinIO, AWS S3) instead of on local disk. Setting only some of them is a startup
error, because silently falling back to disk loses uploads on the next deploy.

```bash
S3_ENDPOINT_URL=http://your-storage-host:8333
S3_BUCKET=your-bucket
S3_ACCESS_KEY_ID=your-access-key
S3_SECRET_ACCESS_KEY=your-secret-key
S3_REGION=us-east-1            # optional, defaults to us-east-1
S3_ADDRESSING_STYLE=path       # optional; SeaweedFS and MinIO need "path"
```

Videos are keyed `raw/<filename>`, and demo videos `demo/<filename>`, in the
same bucket. The API and the worker must point at the same bucket.

## Authentication

No external identity provider is configured. Every request resolves to a single
local user, and no token is needed on any endpoint. Do not expose this
deployment to an untrusted network without putting authentication in front of
it.

All data (videos, players, serve windows) is scoped by `user_id`.

## Development

### Code quality

Pre-commit hooks run ruff automatically on `git commit`. To run manually:

```bash
cd backend
ruff format .
ruff check . --fix
```

Or inside Docker:

```bash
docker compose exec backend ruff check . --fix
docker compose exec backend ruff format .
```

### Migrations

When editing models, always create a migration and update [`docs/database_schema.md`](docs/database_schema.md).

```bash
# Check current state
docker compose exec backend alembic current

# Auto-generate from model changes
docker compose exec backend alembic revision --autogenerate -m "description"

# Apply
docker compose exec backend alembic upgrade head
```

## Project structure

```
backend/
├── app/
│   ├── api/
│   │   ├── routes/          # FastAPI endpoints
│   │   └── schemas/         # Pydantic request/response models
│   ├── core/
│   │   ├── config.py        # Settings (PROFILE, env vars)
│   │   └── database.py      # DB session setup
│   ├── models/              # SQLAlchemy models
│   ├── services/            # Business logic (no HTTP concerns)
│   ├── dependencies/        # FastAPI dependency injection helpers
│   ├── utils/               # Error handling, auth helpers, logging, rate limiting
│   └── main.py              # FastAPI app entry point
├── ml_models/               # Pre-trained model weights (MediaPipe pose, YOLO ball detection)
├── scripts/                 # Utility scripts (backfill, annotation, DB tools)
├── docs/                    # Topic docs (see docs/README.md)
├── alembic/                 # DB migrations
├── tests/                   # pytest tests
└── pyproject.toml           # Python project config and deps
```

## Docs

- [`docs/README.md`](docs/README.md) - index
- [`docs/config.md`](docs/config.md) - full environment variable reference
- [`docs/background-jobs.md`](docs/background-jobs.md) - RQ job patterns
- [`docs/database_schema.md`](docs/database_schema.md) - schema reference
- [`docs/deploy-flyio.md`](docs/deploy-flyio.md) - (optional) Fly.io deployment
- [`docs/demo-videos.md`](docs/demo-videos.md) - (optional) demo video setup

## Troubleshooting

**Port in use:**

```bash
lsof -i :8000
kill -9 <PID>
```

**Database reset:**

```bash
docker compose exec postgres psql -U tennis -c "DROP DATABASE IF EXISTS tennis_coach;"
docker compose exec postgres psql -U tennis -c "CREATE DATABASE tennis_coach;"
docker compose exec backend alembic upgrade head
```

**FFmpeg not found:**

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

**Check video can be read:**

```bash
ffmpeg -i your_video.mp4 -f null -
```
