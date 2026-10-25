"""Minimal Celery producer used by the API process."""

from celery import Celery


class CelerySatelliteJobQueue:
    def __init__(self, broker_url: str) -> None:
        self._client = Celery("jaldrishti-api-producer", broker=broker_url)

    def enqueue(self, job_id: str) -> None:
        self._client.send_task(
            "jaldrishti.satellite.process_event",
            args=[job_id],
            queue="jaldrishti.satellite",
        )
