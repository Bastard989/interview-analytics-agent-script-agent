from interview_analytics_agent.processing.pii import mask_pii


def test_mask_email():
    t = "Почта test@example.com"
    assert "[EMAIL]" in mask_pii(t)


def test_mask_phone():
    t = "Телефон +7 999 123 45 67"
    assert "[PHONE]" in mask_pii(t)
