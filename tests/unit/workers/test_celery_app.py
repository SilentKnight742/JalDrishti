"""Worker configuration tests that do not connect to Redis."""

from jaldrishti_workers.celery_app import create_celery_app
from jaldrishti_workers.tasks import ping


def test_worker_uses_json_and_separate_operational_queues(monkeypatch) -> None:
    monkeypatch.setenv("JALDRISHTI_REDIS_URL", "redis://example.invalid:6379/7")

    app = create_celery_app()

    assert app.conf.broker_url == "redis://example.invalid:6379/7"
    assert app.conf.task_serializer == "json"
    assert app.conf.accept_content == ["json"]
    assert app.conf.task_routes["jaldrishti.satellite.*"]["queue"] == "jaldrishti.satellite"
    assert app.conf.beat_schedule["ingest-nwdp-assam-hourly"] == {
        "task": "jaldrishti.ingestion.nwdp_assam",
        "schedule": 3600.0,
        "options": {"expires": 3300},
    }
    assert app.conf.beat_schedule["ingest-imd-warnings-assam-30m"]["schedule"] == 1800.0
    assert app.conf.beat_schedule["ingest-rainfall-forecast-assam-3h"]["schedule"] == 10800.0
    assert app.conf.beat_schedule["evaluate-assam-events-5m"] == {
        "task": "jaldrishti.events.evaluate_assam",
        "schedule": 300.0,
        "options": {"expires": 240},
    }


def test_ping_task_has_no_external_dependency() -> None:
    result = ping.run()

    assert result["service"] == "jaldrishti-worker"
    assert result["status"] == "ok"
    assert result["executed_at"].endswith("+00:00")
