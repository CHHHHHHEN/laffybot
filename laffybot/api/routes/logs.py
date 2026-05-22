"""Log and error retrieval routes — exposes recent errors for frontend consumption."""

from __future__ import annotations

from fastapi import APIRouter, Query

from laffybot.api.schemas import ErrorLogListResponse, ErrorLogRecord
from laffybot.service.error_log import get_error_log

router = APIRouter()


@router.get("/logs/errors", response_model=ErrorLogListResponse)
async def recent_errors(
    limit: int = Query(default=20, ge=1, le=200),
) -> ErrorLogListResponse:
    """Return the most recent N error records from the in-memory ring buffer.

    Errors are recorded from:
    - SSE stream failures (send_message)
    - Background task failures (async_events)
    - API handler exceptions
    - Any loguru ERROR-level log message
    """
    svc = get_error_log()
    records = svc.recent(limit=limit)
    return ErrorLogListResponse(
        errors=[ErrorLogRecord(**r) for r in records],
        total=svc.count,
    )
