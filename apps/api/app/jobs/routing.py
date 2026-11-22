"""Celery wrapper. Logic lives in app.services.routing_service."""

import asyncio

from app.jobs.celery_app import celery_app
from app.services import routing_service


@celery_app.task(
    name="app.jobs.routing.process_due_routes",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=60,
)
def process_due_routes() -> dict:
    return asyncio.run(routing_service.process_due_routes())
