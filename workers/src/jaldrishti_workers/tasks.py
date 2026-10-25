"""Infrastructure-level tasks used to verify the queue before live adapters exist."""

from datetime import UTC, datetime

from jaldrishti_workers.celery_app import celery_app


@celery_app.task(name="jaldrishti.system.ping")
def ping() -> dict[str, str]:
    """Return deterministic worker identity with a UTC execution timestamp."""

    return {
        "service": "jaldrishti-worker",
        "status": "ok",
        "executed_at": datetime.now(UTC).isoformat(),
    }
