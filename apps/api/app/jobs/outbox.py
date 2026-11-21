import asyncio

from app.jobs.celery_app import celery_app
from app.services import outbox_service


@celery_app.task(name="app.jobs.outbox.process_pending", autoretry_for=(Exception,),
                 max_retries=3, default_retry_delay=30)
def process_pending() -> dict:
    return asyncio.run(outbox_service.process_pending())
