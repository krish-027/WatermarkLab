from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=['Local health'])


class HealthResponse(BaseModel):
    status: Literal['ok'] = 'ok'
    service: Literal['watermarklab-api'] = 'watermarklab-api'
    version: str = '0.2.0'


@router.get('/health', response_model=HealthResponse)
def health() -> HealthResponse:
    """Process liveness only. Does not assert detector or external-service readiness."""
    return HealthResponse()
