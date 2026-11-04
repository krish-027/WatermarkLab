"""Authenticated metadata foundation. Requests retain user tokens and RLS."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.security import Identity, require_user
from app.core.database_diagnostics import development_headers

router = APIRouter(prefix='/api/v1', tags=['Accounts and metadata'])


def database(request: Request, identity: Identity, path: str, method='GET', payload=None, prefer='return=representation', *, operation_stage=None):
    settings = request.app.state.settings
    headers = {'apikey': settings.supabase_publishable_key.get_secret_value(),
               'Authorization': 'Bearer ' + identity.token, 'Content-Type': 'application/json',
               'Prefer': prefer}
    data = json.dumps(payload).encode() if payload is not None else None
    try:
        with urlopen(URLRequest(settings.supabase_url + '/rest/v1/' + path, data=data, headers=headers, method=method), timeout=15) as response:
            body = response.read()
            return json.loads(body) if body else []
    except HTTPError as error:
        diagnostic_headers=development_headers(request,error,operation_stage)
        if error.code in (401, 403):
            raise HTTPException(error.code, 'Database access denied',headers=diagnostic_headers) from None
        raise HTTPException(503, 'Database request failed. Check migration and grants.',headers=diagnostic_headers) from None
    except (URLError, TimeoutError):
        raise HTTPException(503, 'Database unavailable') from None


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    display_name: str = Field(max_length=100)
    retain_text: bool = False


class DraftInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=160)


@router.get('/me')
def me(identity: Identity = Depends(require_user)):
    return {'id': identity.user_id}


@router.get('/profile')
def profile(request: Request, identity: Identity = Depends(require_user)):
    rows = database(request, identity, f'profiles?id=eq.{identity.user_id}&select=id,display_name,retain_text')
    return rows[0] if rows else None


@router.put('/profile')
def save_profile(body: ProfileInput, request: Request, identity: Identity = Depends(require_user)):
    # Atomic first-save creation/update: registration does not depend on a DB trigger.
    return database(request, identity, 'profiles?on_conflict=id', 'POST',
                    {'id': identity.user_id, **body.model_dump()},
                    prefer='return=representation,resolution=merge-duplicates')[0]


@router.get('/experiments')
def experiments(request: Request, identity: Identity = Depends(require_user)):
    return database(request, identity, 'experiments?select=id,title,status,created_at&order=created_at.desc&limit=100')


@router.post('/experiments', status_code=201)
def create_draft(body: DraftInput, request: Request, identity: Identity = Depends(require_user)):
    return database(request, identity, 'experiments', 'POST', {'user_id': identity.user_id, 'title': body.title})[0]


@router.patch('/experiments/{experiment_id}')
def rename_draft(experiment_id: UUID, body: DraftInput, request: Request, identity: Identity = Depends(require_user)):
    rows = database(request, identity, f'experiments?id=eq.{experiment_id}', 'PATCH', body.model_dump())
    if not rows:
        raise HTTPException(404, 'Experiment not found')
    return rows[0]


@router.delete('/experiments/{experiment_id}', status_code=204)
def delete_draft(experiment_id: UUID, request: Request, identity: Identity = Depends(require_user)):
    rows = database(request, identity, f'experiments?id=eq.{experiment_id}', 'DELETE')
    if not rows:
        raise HTTPException(404, 'Experiment not found')
    return Response(status_code=204)
