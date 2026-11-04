"""Ephemeral paired experiments. Persistent result writes remain restricted."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool
from pydantic import Field, StrictBool
from app.core.security import Identity, require_user
from app.schemas.analysis import AnalysisInput, AnalysisResult
from app.schemas.transformation import TransformInput
from app.services.gemini_service import GeminiFailure
from app.services.robustness_edits import transform, VERSION
from app.services.run_receipts import issue

router=APIRouter(prefix='/api/v1',tags=['Robustness research'])

class ComparisonInput(AnalysisInput):
    operation: Literal['minor_edit','synonym','shorten','paraphrase','restructure']='minor_edit'
    strength: int=Field(default=25,ge=1,le=100,strict=True)
    objective: Literal['preserve','moderate','substantial']='preserve'
    external_processing_consent: StrictBool=False

@router.post('/compare')
async def compare(body:ComparisonInput,request:Request,response:Response,user:Identity=Depends(require_user)):
    response.headers['Cache-Control']='no-store'
    settings=request.app.state.settings
    if len(body.text)>settings.analysis_max_characters:
        raise HTTPException(413,'Source exceeds configured limit')
    adapter=request.app.state.kgw if body.method=='KGW' else request.app.state.synthid
    original=AnalysisInput(**body.model_dump(include=set(AnalysisInput.model_fields)))
    try:
        baseline=await run_in_threadpool(adapter.analyze,original,settings.analysis_max_tokens)
        if baseline.compatibility_status!='declared' or baseline.verdict=='UNAVAILABLE':
            # Do not spend paid quota on an unsupported experiment.
            return {'status':'not_run','baseline':baseline.model_dump(),'message':'A runnable, explicitly compatible baseline profile is required.'}
        provider=None
        if body.operation in ('paraphrase','restructure'):
            if not body.external_processing_consent:
                raise HTTPException(422,'Explicit external-processing consent is required')
            if len(body.text)>4000:
                raise HTTPException(413,'Gemini source limit is 4000 characters')
            provider=await request.app.state.gemini.transform(TransformInput(text=body.text,operation=body.operation,objective=body.objective,external_processing_consent=True))
            changed=provider.transformed_text
            edits=[]
        else:
            edited=transform(body.text,body.operation,strength=body.strength)
            changed=edited.text
            edits=[{'start':e.start,'end':e.end,'before':e.before,'after':e.after,'rule':e.rule} for e in edited.edits]
        child_input=original.model_copy(update={'text':changed,'provenance':'UNKNOWN'})
        if len(changed)>settings.analysis_max_characters:
            after=AnalysisResult(method=body.method,profile_id=body.profile_id,verdict='INCONCLUSIVE',provenance='UNKNOWN',character_count=len(changed),warnings=['Child exceeds configured character limit; not scored.'])
        else:
            try:
                after=await run_in_threadpool(adapter.analyze,child_input,settings.analysis_max_tokens)
            except Exception:
                # Preserve the completed transformation and actual paid usage.
                # Do not retry generation because child analysis was unavailable.
                after=AnalysisResult(method=body.method,profile_id=body.profile_id,verdict='UNAVAILABLE',provenance='UNKNOWN',character_count=len(changed),warnings=['Child detection could not complete. Transformation and provider usage are retained in this ephemeral response.'])
    except BlockingIOError:
        raise HTTPException(429,'Detector busy; retry manually. A completed Gemini request may have used quota.') from None
    except GeminiFailure as error:
        raise HTTPException(error.status,{'code':error.code,'message':error.message,'retryable':error.retryable}) from None
    after.compatibility_basis='Residual-signal experiment using the original declared profile; not proof of compatible generation of the child.'
    usable=baseline.verdict in ('DETECTED','NOT DETECTED') and after.verdict in ('DETECTED','NOT DETECTED') and baseline.threshold==after.threshold and baseline.profile_id==after.profile_id
    field='z_score' if body.method=='KGW' else 'p_value'
    before_score,after_score=getattr(baseline,field),getattr(after,field)
    delta=after_score-before_score if usable and before_score is not None and after_score is not None else None
    root_id=str(uuid4())
    result={'status':'completed','experiment_id':str(uuid4()),'created_at':datetime.now(timezone.utc).isoformat(),
        'original':{'id':root_id,'parent_sample_id':None,'text':body.text,'detection':baseline.model_dump()},
        'child':{'id':str(uuid4()),'parent_sample_id':root_id,'text':changed,'detection':after.model_dump()},
        'transformation':{'operation':body.operation,'strength':body.strength,'objective':body.objective,'version':VERSION if provider is None else provider.prompt_version,'edits':edits,'provider':provider.model_dump(exclude={'transformed_text'}) if provider else None},
        'comparison':{'evidence_field':field,'delta':delta,'comparable':usable,'character_delta':len(changed)-len(body.text),'token_delta':after.token_count-baseline.token_count if after.token_count is not None and baseline.token_count is not None else None,'decision_changed':baseline.verdict!=after.verdict if usable else None},
        'semantic':{'method':'manual side-by-side review','score':None,'status':'review required','omissions':'Not assessed','factual_changes':'Not assessed','embedding_status':'unavailable; no semantic model installed'},
        'warnings':['This is one paired observation, not population robustness or watermark removal evidence.','Child watermark provenance is UNKNOWN. Residual scoring does not verify production Gemini watermarks.','Review meaning, omitted claims, names, numbers and factual changes manually.','Ephemeral experiment: not saved to a database.']}
    result['receipt']=None
    try:
        result['receipt']=issue(result,user.user_id,settings.robustness_signing_key.get_secret_value(),settings.robustness_signing_key_id)
    except ValueError:
        result['warnings'].append('Saving setup unavailable; comparison remains ephemeral.')
    return result
