from app.intelligence import _intake_ai_attachment_parts


def test_whatsapp_video_is_retained_for_review_not_sent_as_input_file():
    parts = _intake_ai_attachment_parts(
        {"original_filename": "whatsapp-video.mp4", "media_type": "video/mp4"},
        b"video bytes",
    )
    assert parts[0]["type"] == "input_text"
    assert "retained in the intake record" in parts[0]["text"]
    assert "requiring human review" in parts[0]["text"]
    assert "file_data" not in parts[0]


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
    parts = _intake_ai_attachment_parts(
        {"original_filename": "clip.mov", "media_type": "application/octet-stream"},
        b"movie bytes",
    )
    assert parts[0]["type"] == "input_text"
    assert "file_data" not in parts[0]
