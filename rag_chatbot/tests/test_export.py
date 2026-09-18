from utils.export import transcript_markdown


def test_transcript_export_is_stable():
    result = transcript_markdown([{"role": "user", "content": "Hello"}])
    assert "Hello" in result