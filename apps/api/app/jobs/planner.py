"""Celery task wrappers. All logic lives in app.services.planner_service."""
import asyncio

from app.jobs.celery_app import celery_app
from app.services import planner_service


@celery_app.task(name="app.jobs.planner.generate_tasks_for_due", autoretry_for=(Exception,),
                 max_retries=3, default_retry_delay=60)
def generate_tasks_for_due() -> dict:
    return asyncio.run(planner_service.generate_tasks_for_due())


@celery_app.task(name="app.jobs.planner.check_stale_leads", autoretry_for=(Exception,),
                 max_retries=3, default_retry_delay=60)
def check_stale_leads() -> dict:
    return asyncio.run(planner_service.check_stale_leads())


@celery_app.task(name="app.jobs.planner.emit_overdue_alerts", autoretry_for=(Exception,),
                 max_retries=3, default_retry_delay=60)
def emit_overdue_alerts() -> dict:
    return asyncio.run(planner_service.emit_overdue_alerts())
