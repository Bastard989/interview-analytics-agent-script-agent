from interview_analytics_agent.processing.enhancer import enhance_text


def test_enhancer_adds_punct():
    text, meta = enhance_text("привет")
    assert text.endswith(".")
    assert "final_punct" in meta["applied"]
