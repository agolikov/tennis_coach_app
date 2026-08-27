"""Tests for HTTP Range handling in the video streaming service.

Scrubbing the timeline is the core interaction of this app, and it works only
if ranged requests are answered correctly. These tests pin the parsing rules
and the 206 response shape.
"""

from unittest.mock import Mock, patch

import pytest

from app.services.video_streaming_service import (
    _parse_range_header,
    get_video_stream_response,
)

FILE_SIZE = 1000


class TestParseRangeHeader:
    """Tests for _parse_range_header."""

    def test_none_header_means_whole_file(self) -> None:
        assert _parse_range_header(None, FILE_SIZE) is None

    def test_empty_header_means_whole_file(self) -> None:
        assert _parse_range_header("", FILE_SIZE) is None

    def test_bounded_range(self) -> None:
        assert _parse_range_header("bytes=0-499", FILE_SIZE) == (0, 499)

    def test_open_ended_range_runs_to_last_byte(self) -> None:
        assert _parse_range_header("bytes=500-", FILE_SIZE) == (500, 999)

    def test_suffix_range_returns_final_bytes(self) -> None:
        """"bytes=-500" means the last 500 bytes, not the first 500."""
        assert _parse_range_header("bytes=-500", FILE_SIZE) == (500, 999)

    def test_suffix_larger_than_file_clamps_to_start(self) -> None:
        assert _parse_range_header("bytes=-5000", FILE_SIZE) == (0, 999)

    def test_end_past_eof_is_clamped(self) -> None:
        """A player may ask past the end; answer with what exists."""
        assert _parse_range_header("bytes=900-99999", FILE_SIZE) == (900, 999)

    def test_start_past_eof_is_unsatisfiable(self) -> None:
        assert _parse_range_header("bytes=5000-6000", FILE_SIZE) is None

    def test_inverted_range_rejected(self) -> None:
        assert _parse_range_header("bytes=500-100", FILE_SIZE) is None

    def test_whitespace_tolerated(self) -> None:
        assert _parse_range_header("  bytes=0-99  ", FILE_SIZE) == (0, 99)

    @pytest.mark.parametrize(
        "header",
        ["items=0-99", "bytes=abc-def", "bytes=", "0-99", "bytes=-", "bytes 0-99"],
    )
    def test_malformed_headers_fall_back_to_whole_file(self, header: str) -> None:
        assert _parse_range_header(header, FILE_SIZE) is None

    def test_single_byte_range(self) -> None:
        assert _parse_range_header("bytes=0-0", FILE_SIZE) == (0, 0)


class TestStreamResponse:
    """Tests for the response the stream endpoint builds from object storage."""

    def _video(self) -> Mock:
        video = Mock()
        video.file_path = "raw/clip.mp4"
        video.filename = "clip.mp4"
        video.content_type = "video/mp4"
        video.is_active_demo = False
        return video

    def test_full_request_advertises_range_support(self) -> None:
        """A plain GET must advertise Accept-Ranges or the browser won't seek."""
        body = Mock()
        body.read.side_effect = [b"data", b""]

        with patch(
            "app.services.video_streaming_service.storage_service"
        ) as mock_storage:
            mock_storage.is_remote = True
            mock_storage.get_object_size.return_value = FILE_SIZE
            mock_storage.open_range_stream.return_value = (body, FILE_SIZE)

            response = get_video_stream_response(self._video(), range_header=None)

        assert response.status_code == 200
        assert response.headers["accept-ranges"] == "bytes"
        assert response.headers["content-length"] == str(FILE_SIZE)

    def test_ranged_request_returns_206_with_content_range(self) -> None:
        """A ranged GET must answer 206 with a correct Content-Range."""
        body = Mock()
        body.read.side_effect = [b"data", b""]

        with patch(
            "app.services.video_streaming_service.storage_service"
        ) as mock_storage:
            mock_storage.is_remote = True
            mock_storage.get_object_size.return_value = FILE_SIZE
            mock_storage.open_range_stream.return_value = (body, 500)

            response = get_video_stream_response(
                self._video(), range_header="bytes=0-499"
            )

        assert response.status_code == 206
        assert response.headers["content-range"] == f"bytes 0-499/{FILE_SIZE}"
        assert response.headers["content-length"] == "500"
        mock_storage.open_range_stream.assert_called_once_with("raw/clip.mp4", 0, 499)

    def test_unsatisfiable_range_falls_back_to_full_body(self) -> None:
        """Rather than 416, serve the whole object; players recover from that."""
        body = Mock()
        body.read.side_effect = [b"data", b""]

        with patch(
            "app.services.video_streaming_service.storage_service"
        ) as mock_storage:
            mock_storage.is_remote = True
            mock_storage.get_object_size.return_value = FILE_SIZE
            mock_storage.open_range_stream.return_value = (body, FILE_SIZE)

            response = get_video_stream_response(
                self._video(), range_header="bytes=9999-"
            )

        assert response.status_code == 200
