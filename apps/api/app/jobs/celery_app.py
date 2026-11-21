from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "agrodesk",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.jobs.planner", "app.jobs.outbox"],
)
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_default_queue="agrodesk",
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

# Schedule (UTC). IST = UTC + 5:30
celery_app.conf.beat_schedule = {
    "generate-tasks-nightly": {
        "task": "app.jobs.planner.generate_tasks_for_due",
        "schedule": crontab(minute=0, hour=19),
    },
    "check-stale-daily": {
        "task": "app.jobs.planner.check_stale_leads",
        "schedule": crontab(minute=30, hour=20),
    },
    "emit-overdue-hourly": {
        "task": "app.jobs.planner.emit_overdue_alerts",
        "schedule": crontab(minute=35, hour="2-15"),
    },
    "outbox-process-every-minute": {
        "task": "app.jobs.outbox.process_pending",
        "schedule": 60.0,  # seconds
    },
}
