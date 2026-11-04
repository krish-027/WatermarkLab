from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.security import Identity, require_user
from app.schemas.analysis import AnalysisInput, AnalysisResult
from app.core.config import BACKEND_ROOT
from app.watermark.synthid_adapter import PROFILE_ID as SYNTHID_PROFILE
import json

router = APIRouter(prefix='/api/v1', tags=['analysis'])

@router.get('/kgw/samples')
def samples(user: Identity = Depends(require_user)):
    path = BACKEND_ROOT / 'research/kgw_pilot.json'
    if not path.is_file():
        raise HTTPException(503, 'Controlled sample fixtures are not installed')
    data = json.loads(path.read_text(encoding='utf-8'))
    return [dict(id=row['id'], text=row['text'], provenance=row['provenance'],
                 label_source=row['label_source'], profile_id=data['profile_id']) for row in data['samples']]

@router.get('/synthid/samples')
def synthid_samples(user: Identity = Depends(require_user)):
    path=BACKEND_ROOT/'research/synthid_pilot.json'
    if not path.is_file():
        raise HTTPException(503,'Controlled SynthID fixtures are not installed')
    data=json.loads(path.read_text(encoding='utf-8'))
    # Do not offer the incompatible HF hash-scheme fixtures to this profile.
    return [dict(id=f'synthid-pilot-{i//2+1}-'+('wm' if row['provenance']=='KNOWN_WATERMARKED' else 'control'),
                 text=row['text'],provenance=row['provenance'],label_source=row['label_source'],
                 profile_id=SYNTHID_PROFILE) for i,row in enumerate(data['samples'])
            if row['implementation']=='deepmind-threefry']

@router.get('/capabilities')
def capabilities(request: Request):
    return {'detectors': [request.app.state.kgw.capabilities(),request.app.state.synthid.capabilities()],
            'max_characters': request.app.state.settings.analysis_max_characters,
            'max_tokens': request.app.state.settings.analysis_max_tokens,
            'retains_text': False}

@router.post('/analyze', response_model=AnalysisResult)
def analyze(payload: AnalysisInput, request: Request, user: Identity = Depends(require_user)):
    settings = request.app.state.settings
    if len(payload.text) > settings.analysis_max_characters:
        raise HTTPException(413, 'Text exceeds the configured character limit')
    try:
        adapter=request.app.state.kgw if payload.method=='KGW' else request.app.state.synthid
        return adapter.analyze(payload, settings.analysis_max_tokens)
    except BlockingIOError:
        raise HTTPException(429, 'Detector is busy. Retry shortly.', headers={'Retry-After': '2'}) from None
