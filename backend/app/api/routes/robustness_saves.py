"""User-scoped transport of internally signed evidence; no service-role key."""
from uuid import UUID
from fastapi import APIRouter,Depends,Request,Response,HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictBool,field_validator
from app.core.security import Identity,require_user
from app.api.routes.accounts import database
from app.services.run_receipts import verify
from typing import Literal

router=APIRouter(prefix='/api/v1/robustness/runs',tags=['Saved robustness runs'])

class ManualReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    meaning:Literal['yes','no','uncertain','not_reviewed']='not_reviewed'
    omissions:Literal['yes','no','uncertain','not_reviewed']='not_reviewed'
    facts:Literal['yes','no','uncertain','not_reviewed']='not_reviewed'

class SaveInput(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    payload:str=Field(max_length=32768,repr=False)
    signature:str=Field(pattern='^[0-9a-f]{64}$',repr=False)
    key_id:str=Field(pattern='^[a-zA-Z0-9_-]{1,32}$')
    original_text:str|None=Field(default=None,max_length=20000,repr=False)
    child_text:str|None=Field(default=None,max_length=20000,repr=False)
    retain_text:StrictBool=False
    save_consent:StrictBool
    manual_review:ManualReview=Field(default_factory=ManualReview)

    @field_validator('save_consent')
    @classmethod
    def consent(cls,value):
        if not value:raise ValueError('Explicit saving consent required')
        return value

@router.post('')
def save(body:SaveInput,request:Request,response:Response,user:Identity=Depends(require_user)):
    response.headers['Cache-Control']='no-store'
    settings=request.app.state.settings
    if body.key_id!=settings.robustness_signing_key_id:raise HTTPException(422,'Unknown receipt key')
    try: doc=verify(body.model_dump(include={'payload','signature','key_id'}),user.user_id,settings.robustness_signing_key.get_secret_value())
    except (ValueError,KeyError,TypeError):raise HTTPException(422,'Receipt invalid, expired or signing setup unavailable') from None
    if body.retain_text!=(body.original_text is not None and body.child_text is not None) or (not body.retain_text and (body.original_text is not None or body.child_text is not None)):
        raise HTTPException(422,'Text retention requires explicit consent for both samples')
    database(request,user,'rpc/save_robustness_run','POST',body.model_dump(exclude={'save_consent'}),operation_stage='save_rpc')
    rows=database(request,user,f"robustness_runs?experiment_id=eq.{UUID(doc['id'])}&select=experiment_id,manifest,manual_review,created_at",operation_stage='readback')
    if len(rows)!=1:raise HTTPException(503,'Save acknowledgement could not be verified; retry manually with the same receipt')
    return {'status':'saved','run':rows[0]}

@router.get('/{run_id}')
def retrieve(run_id:UUID,request:Request,response:Response,user:Identity=Depends(require_user)):
    response.headers['Cache-Control']='no-store'
    rows=database(request,user,f'robustness_runs?experiment_id=eq.{run_id}&select=experiment_id,manifest,manual_review,created_at',operation_stage='readback')
    if not rows:raise HTTPException(404,'Saved run not found')
    return rows[0]
