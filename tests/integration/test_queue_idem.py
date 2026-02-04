from interview_analytics_agent.queue.idempotency import check_and_set


def test_idempotency_placeholder():
    # Этот тест требует поднятого redis — в CI подключим позже
    # Сейчас оставляем как заглушку, чтобы структура была готова.
    assert callable(check_and_set)
