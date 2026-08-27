"""Service for video streaming and URL generation.

Video bytes are always served from the app's own origin, never by redirecting
the browser to the object store. Two things depend on that: the serve thumbnail
strip draws frames into a canvas and calls ``toDataURL()``, which a cross-origin
video would taint, and the app has to keep working when it is reached through a
tunnel or from a device that cannot route to the storage host.
"""

import logging
import re
from typing import Iterator, Optional

from fastapi import Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.models.video import Video
from app.services import video_service
from app.services.storage_service import STREAM_CHUNK_SIZE, storage_service
from app.utils.file_validation import get_safe_filename, validate_file_exists

logger = logging.getLogger(__name__)

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _parse_range_header(
    range_header: Optional[str], file_size: int
) -> Optional[tuple[int, int]]:
    """Parse a single-range HTTP Range header into inclusive byte offsets.

    Args:
        range_header: Raw header value, e.g. "bytes=0-1023"
        file_size: Total size of the object in bytes

    Returns:
        (start, end) inclusive, or None when the header is absent or unusable
        and the full object should be sent instead.
    """
    if not range_header:
        return None

    match = _RANGE_RE.match(range_header.strip())
    if not match:
        return None

    raw_start, raw_end = match.group(1), match.group(2)

    if not raw_start and not raw_end:
        return None

    if not raw_start:
        # "bytes=-500" means the final 500 bytes.
        length = int(raw_end)
        if length <= 0:
            return None
        start = max(0, file_size - length)
        end = file_size - 1
    else:
        start = int(raw_start)
        end = int(raw_end) if raw_end else file_size - 1

    # Clamp to the object; a start past the end is unsatisfiable.
    end = min(end, file_size - 1)
    if start > end or start >= file_size:
        return None

    return start, end


def _iter_body(body: object, chunk_size: int = STREAM_CHUNK_SIZE) -> Iterator[bytes]:
    """Yield an object-storage body in chunks, closing it when finished."""
    try:
        while True:
            chunk = body.read(chunk_size)  # type: ignore[attr-defined]
            if not chunk:
                break
            yield chunk
    finally:
        close = getattr(body, "close", None)
        if close is not None:
            close()


def get_video_stream_response(
    db_video: Video,
    current_user: Optional[dict] = None,
    range_header: Optional[str] = None,
) -> Response:
    """Get streaming response for a video.

    The caller is responsible for fetching db_video and closing the DB session
    before calling this function — the session must not be held open while
    the response streams, or it will exhaust the connection pool.

    Args:
        db_video: Already-fetched Video ORM object
        current_user: Optional user dict (used for logging only)
        range_header: Raw HTTP Range header from the client, if any

    Returns:
        Response object (FileResponse or StreamingResponse)

    Raises:
        RuntimeError: If storage operations fail
    """
    filename = get_safe_filename(db_video.filename)
    media_type = db_video.content_type or "video/mp4"

    if not storage_service.is_remote:
        # FileResponse implements Range handling itself.
        resolved_path = storage_service.get_local_file_path(db_video.file_path)
        validate_file_exists(resolved_path, db_video.filename)

        return FileResponse(
            path=str(resolved_path),
            media_type=media_type,
            filename=filename,
        )

    storage_path = db_video.file_path
    file_size = storage_service.get_object_size(storage_path)
    byte_range = _parse_range_header(range_header, file_size)

    if byte_range is None:
        body, content_length = storage_service.open_range_stream(storage_path)
        return StreamingResponse(
            _iter_body(body),
            media_type=media_type,
            headers={
                "Content-Length": str(content_length),
                # Without this the browser will not offer scrubbing at all.
                "Accept-Ranges": "bytes",
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )

    start, end = byte_range
    body, content_length = storage_service.open_range_stream(storage_path, start, end)
    logger.debug(
        "Serving range %s-%s of %s (%s bytes)", start, end, storage_path, content_length
    )

    return StreamingResponse(
        _iter_body(body),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


def get_video_url(
    db: Session,
    video_id: int,
    current_user: Optional[dict] = None,
) -> str:
    """Get the URL a client should use to fetch a video.

    Always the app's own stream endpoint — see the module docstring for why the
    object store is not exposed to browsers directly.

    Args:
        db: Database session
        video_id: Video ID
        current_user: Optional user dict for authorization

    Returns:
        Relative URL string for the stream endpoint

    Raises:
        ValueError: If the video is not found
    """
    db_video = video_service.get_video_by_id(db, video_id)
    if not db_video:
        raise ValueError(f"Video with ID {video_id} not found")

    return f"/v0/videos/{video_id}/stream"
