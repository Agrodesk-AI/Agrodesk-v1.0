from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "agrodesk",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.jobs.planner"],
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
    # 00:30 IST = 19:00 UTC
    "generate-tasks-nightly": {
        "task": "app.jobs.planner.generate_tasks_for_due",
        "schedule": crontab(minute=0, hour=19),
    },
    # 02:00 IST = 20:30 UTC
    "check-stale-daily": {
        "task": "app.jobs.planner.check_stale_leads",
        "schedule": crontab(minute=30, hour=20),
    },
    # Hourly during IST business hours 08:05-21:05 = UTC 02:35-15:35
    "emit-overdue-hourly": {
        "task": "app.jobs.planner.emit_overdue_alerts",
        "schedule": crontab(minute=35, hour="2-15"),
    },
}
