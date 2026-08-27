# Configuration (PROFILE-based)

Two things are configured independently:

- **Database**: `DATABASE_URL` if set, otherwise auto-detected — the `postgres`
  host inside Docker, `localhost` outside.
- **Storage**: an S3-compatible bucket when all four `S3_*` variables are set,
  otherwise the local filesystem. Setting only some of them is a startup error.

`PROFILE` now only selects processing limits (`local` allows larger, longer
uploads than `production`). There is no external identity provider: every
request resolves to a single local user.

## Minimal env vars

### Local (recommended)

```bash
PROFILE=local
```

### With object storage

```bash
DATABASE_URL=postgresql://...

S3_ENDPOINT_URL=http://your-storage-host:8333
S3_BUCKET=tennis-coach
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_REGION=us-east-1          # optional
S3_ADDRESSING_STYLE=path     # SeaweedFS/MinIO need path-style

REDIS_URL=rediss://...  # optional — defaults to redis://localhost:6379/0; use Upstash in real prod
SERVICE_TYPE=api-only   # API container when a dedicated worker is deployed
ADMIN_USER_IDS=uuid1,uuid2  # optional — required for admin UI and demo video management
SUPABASE_DEMO_BUCKET=demo-videos  # optional — only needed if using public demo videos
```

### LLM Coaching (optional)

```bash
ANTHROPIC_API_KEY=sk-ant-...  # Required for coaching feedback generation
LLM_MODEL=claude-sonnet-4-6  # optional — defaults to claude-sonnet-4-6
LLM_MAX_TOKENS=1024           # optional — max output tokens for coaching calls
LLM_LOG_DIR=                  # optional — defaults to ../data/llm_logs/
```

## Notes

- `AUTO_CONTACT_DETECTOR_VERSION` controls auto-contact logic:
  - `v1` (default): toss-peak-gated wrist proximity.
  - `v2`: phase-gated proximity (search starts at dominant-arm acceleration onset).
- `AUTO_BALL_DETECTION_ON_UPLOAD` (default `False`) gates whether the
  upload pipeline runs YOLO ball detection automatically. Default is off
  because cleanup of serve windows almost always invalidates the auto-run;
  use the "Re-run ball detection" button in `ServeWindowsPanel` after
  cleanup. Set to `True` to restore the always-run-on-upload behaviour.
- Don’t duplicate “API reference” docs: use `http://localhost:8000/docs`.
- Keep `.env` permissive; the profile decides what’s required.
