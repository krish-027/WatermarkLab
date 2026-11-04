"""Mocked Google transport and detector failures, no paid requests."""
from unittest.mock import AsyncMock,Mock
from fastapi.testclient import TestClient
from google.genai import types
import pytest
from app.core.config import Settings
from app.core.security import Identity,require_user
from app.main import create_app
from app.schemas.analysis import AnalysisResult
from app.services.gemini_service import GeminiFailure
from test_gemini import response_json

@pytest.fixture
def setup():
    app=create_app(Settings(_env_file=None,gemini_api_key='unit-only',gemini_min_interval_seconds=0))
    app.dependency_overrides[require_user]=lambda:Identity('11111111-1111-4111-8111-111111111111','unit')
    baseline=AnalysisResult(method='KGW',profile_id='kgw-gpt2-cpu-v1',verdict='DETECTED',provenance='UNKNOWN',character_count=80,compatibility_status='declared',threshold=4,z_score=5)
    app.state.kgw.analyze=Mock(return_value=baseline)
    app.state.gemini._request=AsyncMock(return_value=types.GenerateContentResponse.model_validate(response_json()))
    body={'text':'A researcher watered two seedlings daily and measured their growth for one week.','method':'KGW','profile_id':'kgw-gpt2-cpu-v1','compatibility_confirmed':True,'operation':'paraphrase','external_processing_consent':True}
    with TestClient(app) as client:yield app,client,body,baseline

def test_child_failure_preserves_completed_generation_usage(setup):
    app,client,body,baseline=setup
    app.state.kgw.analyze.side_effect=[baseline,BlockingIOError()]
    data=client.post('/api/v1/compare',json=body).json()
    assert data['child']['detection']['verdict']=='UNAVAILABLE'
    assert data['comparison']['delta'] is None
    assert data['transformation']['provider']['usage']['total_tokens']==140
    assert app.state.gemini._request.await_count==1

def test_missing_consent_never_calls_google(setup):
    app,client,body,_=setup;body['external_processing_consent']=False
    assert client.post('/api/v1/compare',json=body).status_code==422
    assert app.state.gemini._request.await_count==0

@pytest.mark.parametrize('code,status',[('TIMEOUT',504),('PROVIDER_RATE_LIMIT',429),('INVALID_RESPONSE',502)])
def test_google_failure_does_not_score_child_or_retry(setup,code,status):
    app,client,body,_=setup
    app.state.gemini._request.side_effect=GeminiFailure(code,'Safe unit error',status)
    response=client.post('/api/v1/compare',json=body)
    assert response.status_code==status and response.json()['detail']['code']==code
    assert app.state.kgw.analyze.call_count==1
    assert app.state.gemini._request.await_count==1

def test_existing_gemini_concurrency_lock_prevents_second_paid_call(setup):
    app,client,body,_=setup
    app.state.gemini._lock.acquire()
    try:assert client.post('/api/v1/compare',json=body).status_code==429
    finally:app.state.gemini._lock.release()
    assert app.state.gemini._request.await_count==0
