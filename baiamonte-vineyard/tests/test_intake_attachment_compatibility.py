from unittest.mock import patch

from app.intelligence import _intake_ai_attachment_parts, _intake_video_frame_parts


def test_whatsapp_video_is_analyzed_as_representative_frames():
    extracted = [{"type": "input_text", "text": "frames"}, {"type": "input_image", "image_url": "data:image/jpeg;base64,Zm9v"}]
    with patch("app.intelligence._intake_video_frame_parts", return_value=extracted) as frame_parts:
        parts = _intake_ai_attachment_parts(
            {"original_filename": "whatsapp-video.mp4", "media_type": "video/mp4"},
            b"video bytes",
        )
    frame_parts.assert_called_once_with(b"video bytes", "whatsapp-video.mp4", "video/mp4")
    assert parts == extracted
    assert all("file_data" not in part for part in parts)


def test_supported_image_remains_visual_input():
    parts = _intake_ai_attachment_parts(
        {"original_filename": "field.jpg", "media_type": "image/jpeg"},
        b"jpeg bytes",
    )
    assert parts == [{"type": "input_image", "image_url": "data:image/jpeg;base64,anBlZyBieXRlcw=="}]


def test_supported_document_remains_file_input():
    parts = _intake_ai_attachment_parts(
        {"original_filename": "laboratory.pdf", "media_type": "application/pdf"},
        b"pdf bytes",
    )
    assert parts == [{
        "type": "input_file",
        "filename": "laboratory.pdf",
        "file_data": "data:application/pdf;base64,cGRmIGJ5dGVz",
    }]


def test_spoofed_video_extension_is_not_sent_as_octet_stream_file():
    with patch("app.intelligence._intake_video_frame_parts", return_value=[{"type": "input_text", "text": "frames"}]) as frame_parts:
        parts = _intake_ai_attachment_parts(
            {"original_filename": "clip.mov", "media_type": "application/octet-stream"},
            b"movie bytes",
        )
    frame_parts.assert_called_once()
    assert all("file_data" not in part for part in parts)


def test_undecodable_video_is_retained_without_guessing():
    with patch("app.intelligence.subprocess.run", side_effect=OSError("decoder unavailable")):
        parts = _intake_video_frame_parts(b"not a video", "clip.mp4", "video/mp4")
    assert parts[0]["type"] == "input_text"
    assert "could not be decoded" in parts[0]["text"]
    assert "Do not infer its contents" in parts[0]["text"]
