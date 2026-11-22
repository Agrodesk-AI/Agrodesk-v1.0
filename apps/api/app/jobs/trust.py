"""Celery wrapper. Logic lives in app.services.trust_service."""

import asyncio

from app.jobs.celery_app import celery_app
from app.services import trust_service


@celery_app.task(
    name="app.jobs.trust.recompute_all",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=300,
)
def recompute_all() -> dict:
    return asyncio.run(trust_service.recompute_all())
