from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.db import get_session_tenant
from app.schemas.task import TaskOut, TaskOutcomeIn
from app.services import task_service

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


def _out(t) -> TaskOut:
    return TaskOut(
        id=t.id,
        dealer_id=t.dealer_id,
        lead_id=t.lead_id,
        user_id=t.user_id,
        due_at=t.due_at,
        type=t.type,
        status=t.status,
        outcome=t.outcome,
        completed_at=t.completed_at,
    )


@router.get("/today", response_model=list[TaskOut])
async def today(
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[TaskOut]:
    rows = await task_service.list_today(session, user_id=UUID(principal["user_id"]))
    return [_out(x) for x in rows]


@router.post("/{task_id}/outcome", response_model=TaskOut)
async def outcome(
    task_id: UUID,
    body: TaskOutcomeIn,
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> TaskOut:
    task = await task_service.get(session, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    try:
        task = await task_service.mark_outcome(
            session, task=task, acting_user_id=UUID(principal["user_id"]), outcome=body.outcome
        )
    except task_service.BadOutcome as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"bad_outcome:{e}") from None
    except task_service.TaskNotForYou:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "task_not_yours") from None
    return _out(task)
