"""Celery application shared by the ingestion and intelligence workers."""

from __future__ import annotations

import os

from celery import Celery

DEFAULT_REDIS_URL = "redis://redis:6379/0"


def create_celery_app() -> Celery:
    """Build a worker app from environment-only infrastructure settings."""

    redis_url = os.getenv("JALDRISHTI_REDIS_URL", DEFAULT_REDIS_URL)
    app = Celery(
        "jaldrishti",
        broker=redis_url,
        backend=redis_url,
        include=[
            "jaldrishti_workers.tasks",
            "jaldrishti_workers.ingestion",
            "jaldrishti_workers.weather_ingestion",
            "jaldrishti_workers.event_engine",
            "jaldrishti_workers.satellite",
        ],
    )
    app.conf.update(
        accept_content=["json"],
        broker_connection_retry_on_startup=True,
        enable_utc=True,
        result_accept_content=["json"],
        result_expires=3600,
        task_default_queue="jaldrishti.default",
        task_routes={
            "jaldrishti.ingestion.*": {"queue": "jaldrishti.ingestion"},
            "jaldrishti.satellite.*": {"queue": "jaldrishti.satellite"},
            "jaldrishti.intelligence.*": {"queue": "jaldrishti.intelligence"},
        },
        beat_schedule={
            "ingest-nwdp-assam-hourly": {
                "task": "jaldrishti.ingestion.nwdp_assam",
                "schedule": 3600.0,
                "options": {"expires": 3300},
            },
            "ingest-imd-warnings-assam-30m": {
                "task": "jaldrishti.ingestion.imd_warnings_assam",
                "schedule": 1800.0,
                "options": {"expires": 1500},
            },
            "ingest-rainfall-forecast-assam-3h": {
                "task": "jaldrishti.ingestion.rainfall_forecast_assam",
                "schedule": 10800.0,
                "options": {"expires": 9000},
            },
            "evaluate-assam-events-5m": {
                "task": "jaldrishti.events.evaluate_assam",
                "schedule": 300.0,
                "options": {"expires": 240},
            },
        },
        task_serializer="json",
        timezone="UTC",
        worker_hijack_root_logger=False,
    )
    return app


celery_app = create_celery_app()
