"""Simplified application settings for hobby project."""

import logging
import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings - simplified for hobby project."""

    # ONE setting: local or production
    PROFILE: str = "local"

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = False

    # Database — PostgreSQL. Set DATABASE_URL to point at the managed instance;
    # unset falls back to the local docker-compose/localhost default.
    DATABASE_URL: Optional[str] = None
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 1800
    DB_POOL_PRE_PING: bool = True

    # S3-compatible object storage (SeaweedFS, MinIO, AWS S3).
    # When all four required values are set, this takes precedence over the
    # PROFILE-derived backend and video data lives in the bucket instead of on
    # a mounted volume. Leave unset to keep using local disk.
    S3_ENDPOINT_URL: Optional[str] = None
    S3_BUCKET: Optional[str] = None
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_REGION: str = "us-east-1"
    # SeaweedFS and MinIO need path-style addressing; AWS accepts "virtual".
    S3_ADDRESSING_STYLE: str = "path"

    # Storage paths
    # UPLOAD_DIR/PROCESSED_DIR stay in use as scratch space even on S3:
    # ffmpeg and OpenCV need a real file on disk to transcode and seek.
    UPLOAD_DIR: str = "../data/videos/raw"
    PROCESSED_DIR: str = "../data/videos/processed"
    MAX_FILE_SIZE: int = 419430400  # 400MB
    SUPPORTED_FORMATS: list[str] = [".mp4", ".mov", ".avi", ".mkv", ".wmv"]

    # Redis (optional - defaults to localhost)
    REDIS_URL: Optional[str] = None
    SERVICE_TYPE: Optional[str] = None  # 'api', 'api-only', or 'worker'

    # Background job behavior
    AUTO_ENQUEUE_ON_UPLOAD: bool = False

    # Pipeline automation
    AUTO_ACCEPT_SERVE_PROPOSALS: bool = True
    AUTO_ACCEPT_CONFIDENCE_THRESHOLD: float = 0.6
    AUTO_COMPUTE_BIOMECHANICS: bool = True
    AUTO_CONTACT_DETECTOR_VERSION: str = "v1"
    # Ball detection runs YOLO inference and is expensive (~90s/video).
    # Default off: serve windows almost always need cleanup before they're
    # the right input. Users trigger ball detection manually post-cleanup.
    AUTO_BALL_DETECTION_ON_UPLOAD: bool = False

    # LLM Coaching
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_MODEL: str = "claude-sonnet-4-6"
    LLM_LOG_DIR: Optional[str] = None
    LLM_MAX_TOKENS: int = 1024

    # ML Models
    ML_MODELS_DIR: str = "ml_models"

    # Pose Detection
    POSE_DETECTION_CONFIDENCE: float = 0.5
    POSE_TRACKING_CONFIDENCE: float = 0.5
    POSE_OVERALL_CONFIDENCE: float = 0.8

    # Ball Detection (YOLO)
    # Inference image size. 640 is YOLO default; 1280 ~doubles pixel resolution
    # (better for small/far balls) at ~3-4x inference cost. Native MPS handles
    # 1280 comfortably; Docker CPU does not.
    YOLO_IMGSZ: int = 640

    # Serve Detection
    SERVE_DETECTION_LOW_CONFIDENCE_THRESHOLD: float = (
        0.6  # Proposals below this are "uncertain"
    )

    # Processing limits
    MAX_VIDEO_DURATION: int = 300  # 5 minutes
    FRAME_SKIP_RATIO: int = 1
    MAX_VIDEO_RESOLUTION: tuple[int, int] = (3840, 2160)  # 4K
    MAX_FPS: int = 60
    FPS_TOLERANCE: float = 0.5
    POSE_DETECTION_JOB_TIMEOUT_SECONDS: int = 1800

    # Scout mode settings
    # Process every Nth frame in scout mode. Higher = faster scout, less temporal detail.
    # At 60fps: 2 → 30fps effective, 4 → 15fps, 6 → 10fps. 15fps is usually enough for serve detection.
    SCOUT_FRAME_SKIP: int = 4

    # Transcoding settings
    # Every upload is transcoded to 1080p/30fps H.264 for consistent pose detection input.
    TRANSCODE_ENABLED: bool = True
    TRANSCODE_RESOLUTION: int = 1080  # height in pixels
    TRANSCODE_FPS: int = 30
    TRANSCODE_CRF: int = 18  # quality (lower = better, 18-28 typical)

    # Upload limits (primarily for production)
    # Note: enforced only when PROFILE != "local" and user is not admin.
    MAX_VIDEO_UPLOADS_PER_DAY: int = 20

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://aseda-sam.github.io",
    ]

    # Admin access (comma-separated auth user UUIDs)
    # In PROFILE=local, the auth dependency returns the mock user id below, so local dev
    # can access admin-only endpoints by default.
    ADMIN_USER_IDS: str = "00000000-0000-0000-0000-000000000000"

    # Demo (for demo videos)
    DEMO_USER_ID: str = "00000000-0000-0000-0000-000000000001"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def admin_user_ids(self) -> list[str]:
        """Admin allowlist parsed from ADMIN_USER_IDS env var."""
        return [uid.strip() for uid in self.ADMIN_USER_IDS.split(",") if uid.strip()]

    @property
    def database_url(self) -> str:
        """PostgreSQL URL - explicit DATABASE_URL, else the compose/local default."""
        if self.DATABASE_URL:
            return self.DATABASE_URL

        # Detect if running in Docker (check for /.dockerenv)
        # In Docker, use service name 'postgres'; locally use 'localhost'
        postgres_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
        return f"postgresql://tennis:tennis_dev@{postgres_host}:5432/tennis_coach"

    @property
    def s3_configured(self) -> bool:
        """True when every value needed to talk to the object store is present."""
        return bool(
            self.S3_ENDPOINT_URL
            and self.S3_BUCKET
            and self.S3_ACCESS_KEY_ID
            and self.S3_SECRET_ACCESS_KEY
        )

    @property
    def storage_type(self) -> str:
        """Storage backend: the object store when configured, else local disk."""
        return "s3" if self.s3_configured else "local"

    @property
    def auth_required(self) -> bool:
        """No external auth provider is configured; the app is unauthenticated."""
        return False

    @property
    def redis_url(self) -> str:
        """Get Redis URL - defaults to localhost."""
        return self.REDIS_URL or "redis://localhost:6379/0"

    @property
    def STORAGE_TYPE(self) -> str:  # noqa: N802 - matches existing API
        """Storage type - auto-detected from PROFILE."""
        return self.storage_type

    @property
    def effective_max_file_size(self) -> int:
        """Max file size - smaller in production."""
        return (
            52428800 if self.PROFILE == "production" else self.MAX_FILE_SIZE
        )  # 50MB prod, 400MB local

    @property
    def effective_max_video_duration(self) -> int:
        """Max video duration - smaller in production."""
        return (
            60 if self.PROFILE == "production" else self.MAX_VIDEO_DURATION
        )  # 1min prod, 5min local

    @property
    def effective_frame_skip_ratio(self) -> int:
        """Frame skip ratio."""
        return self.FRAME_SKIP_RATIO


# Create settings
settings = Settings()

# Partial S3 configuration is a deployment mistake worth failing loudly on:
# silently falling back to local disk would write uploads onto ephemeral
# container storage and lose them on the next deploy.
_s3_vars = {
    "S3_ENDPOINT_URL": settings.S3_ENDPOINT_URL,
    "S3_BUCKET": settings.S3_BUCKET,
    "S3_ACCESS_KEY_ID": settings.S3_ACCESS_KEY_ID,
    "S3_SECRET_ACCESS_KEY": settings.S3_SECRET_ACCESS_KEY,
}
_s3_set = [k for k, v in _s3_vars.items() if v]
if _s3_set and len(_s3_set) != len(_s3_vars):
    _s3_missing = [k for k, v in _s3_vars.items() if not v]
    raise ValueError(
        "Incomplete S3 configuration: set all of "
        f"{', '.join(_s3_vars)} or none. Missing: {', '.join(_s3_missing)}"
    )

# Setup logging
# Structured fields (request_id, job_id, video_id) are added
# by StructuredLogFilter and can be included in format if needed
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# The container images no longer mount a persistent volume for video data, so
# local storage inside a container means uploads live on the container's
# writable layer and vanish on the next deploy. Warn loudly rather than lose
# someone's videos quietly.
if settings.storage_type == "local" and os.path.exists("/.dockerenv"):
    logger.warning(
        "Running in a container with local storage and no S3 bucket configured. "
        "Uploaded videos will be written to ephemeral container storage and "
        "LOST on the next deploy or restart. Set S3_ENDPOINT_URL, S3_BUCKET, "
        "S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY to persist them."
    )

# Create local storage directories on startup
for d in [settings.UPLOAD_DIR, settings.PROCESSED_DIR]:
    Path(d).mkdir(parents=True, exist_ok=True)


# Environment limits (for video validation)
def get_environment_limits() -> dict:
    """Get video processing limits - same for Docker and local."""
    return {
        "max_resolution": settings.MAX_VIDEO_RESOLUTION,
        "max_fps": settings.MAX_FPS,
        "frame_skip_ratio": settings.effective_frame_skip_ratio,
        "environment": "docker" if os.path.exists("/.dockerenv") else "local",
    }


env_limits = get_environment_limits()

logger.info(
    f"Profile: {settings.PROFILE}, Storage: {settings.storage_type}, Auth: {settings.auth_required}"
)
