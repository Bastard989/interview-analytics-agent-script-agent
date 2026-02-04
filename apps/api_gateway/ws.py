"""
WebSocket обработчик.

Протокол (MVP):
- клиент присылает JSON {"event_type":"audio.chunk", ...}
- payload содержит base64 audio (content_b64), seq, meeting_id, sample_rate, channels, codec
- gateway сохраняет аудио в локальное хранилище и ставит задачу STT
- воркеры публикуют transcript.update в Redis pubsub channel ws:<meeting_id>
- gateway подписывается и ретранслирует клиенту

Важно:
- в MVP не делаем сложный backpressure, только базовая дедупликация
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from interview_analytics_agent.common.ids import new_idempotency_key
from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.common.utils import b64_decode, safe_dict
from interview_analytics_agent.queue.dispatcher import enqueue_stt
from interview_analytics_agent.queue.idempotency import check_and_set
from interview_analytics_agent.queue.redis import redis_client
from interview_analytics_agent.storage.blob import put_bytes

log = get_project_logger()

ws_router = APIRouter()


async def _forward_pubsub_to_ws(ws: WebSocket, meeting_id: str) -> None:
    """
    Фоновая задача: читает pubsub канал ws:<meeting_id> и шлёт сообщения в websocket.
    Реализация через asyncio.to_thread, потому что redis_client() синхронный.
    """
    channel = f"ws:{meeting_id}"
    r = redis_client()
    pubsub = r.pubsub()
    pubsub.subscribe(channel)

    try:
        while True:
            msg = await asyncio.to_thread(pubsub.get_message, True, 1.0)
            if not msg:
                await asyncio.sleep(0.01)
                continue
            if msg.get("type") != "message":
                continue

            data = msg.get("data")
            if not data:
                continue

            # data ожидаем как JSON-строку
            try:
                await ws.send_text(data)
            except Exception:
                break
    finally:
        try:
            pubsub.unsubscribe(channel)
            pubsub.close()
        except Exception:
            pass


@ws_router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()

    meeting_id: str | None = None
    forward_task: asyncio.Task | None = None

    try:
        while True:
            raw = await ws.receive_text()
            try:
                event = json.loads(raw)
            except Exception:
                await ws.send_text(
                    json.dumps(
                        {"event_type": "error", "code": "bad_json", "message": "Невалидный JSON"}
                    )
                )
                continue

            et = event.get("event_type")
            if et != "audio.chunk":
                await ws.send_text(
                    json.dumps(
                        {
                            "event_type": "error",
                            "code": "bad_event",
                            "message": "Неизвестный event_type",
                        }
                    )
                )
                continue

            meeting_id = event.get("meeting_id")
            if not meeting_id:
                await ws.send_text(
                    json.dumps(
                        {
                            "event_type": "error",
                            "code": "no_meeting_id",
                            "message": "meeting_id обязателен",
                        }
                    )
                )
                continue

            # Запускаем forward только один раз, когда получили meeting_id
            if forward_task is None:
                forward_task = asyncio.create_task(_forward_pubsub_to_ws(ws, meeting_id))

            seq = int(event.get("seq", 0))
            sample_rate = int(event.get("sample_rate", 16000))
            codec = str(event.get("codec", "pcm"))
            channels = int(event.get("channels", 1))
            content_b64 = event.get("content_b64", "")

            idem_key = event.get("idempotency_key") or new_idempotency_key("ws")
            if not check_and_set("audio_chunk", meeting_id, idem_key):
                # Дубликат — игнорируем молча
                continue

            try:
                audio_bytes = b64_decode(content_b64)
            except Exception:
                await ws.send_text(
                    json.dumps(
                        {
                            "event_type": "error",
                            "code": "bad_audio",
                            "message": "content_b64 не декодируется",
                        }
                    )
                )
                continue

            # Сохраняем в S3
            blob_key = f"meetings/{meeting_id}/chunks/{seq}.bin"
            try:
                put_bytes(blob_key, audio_bytes)
            except Exception as e:
                log.error(
                    "storage_put_failed",
                    extra={"meeting_id": meeting_id, "payload": {"err": str(e)[:200]}},
                )
                await ws.send_text(
                    json.dumps(
                        {"event_type": "error", "code": "storage_error", "message": "Ошибка записи чанка"}
                    )
                )
                continue

            # Ставим STT задачу
            enqueue_stt(meeting_id=meeting_id, chunk_seq=seq, blob_key=blob_key)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(
            "ws_fatal",
            extra={
                "payload": {
                    "err": str(e)[:200],
                    "event": safe_dict(event) if 'event' in locals() else None,
                }
            },
        )
    finally:
        if forward_task:
            forward_task.cancel()
