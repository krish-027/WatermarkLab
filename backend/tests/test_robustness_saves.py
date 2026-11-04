"""Save transport contracts with mocked database, not hosted persistence proof."""
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.core.security import Identity, require_user
from app.api.routes import robustness_saves
from app.services.run_receipts import issue
from test_run_receipts import run, OWNER, KEY

@pytest.fixture
def setup(monkeypatch):
    app=create_app(Settings(_env_file=None,robustness_signing_key=KEY))
    app.dependency_overrides[require_user]=lambda:Identity(OWNER,'dummy-token')
    calls=[]
    def database(request,user,path,method='GET',body=None,*,operation_stage=None):
        calls.append((path,method,body))
        return [{'experiment_id':run()['experiment_id']}] if method=='GET' else run()['experiment_id']
    monkeypatch.setattr(robustness_saves,'database',database)
    with TestClient(app) as client:yield client,calls

def body():return {**issue(run(),OWNER,KEY),'save_consent':True}

def test_save_requires_readback_and_uses_user_transport(setup):
    client,calls=setup
    response=client.post('/api/v1/robustness/runs',json=body())
    assert response.status_code==200 and response.json()['status']=='saved'
    assert response.headers['cache-control']=='no-store'
    assert [c[1] for c in calls]==['POST','GET']
    assert calls[0][2]['original_text'] is None
    assert 'save_consent' not in calls[0][2]

@pytest.mark.parametrize('change',[{'save_consent':False},{'signature':'0'*64},{'original_text':'private-marker'},{'key_id':'unknown'},{'manual_review':{'meaning':'private-marker'}}])
def test_invalid_save_never_calls_database(setup,change):
    client,calls=setup
    response=client.post('/api/v1/robustness/runs',json={**body(),**change})
    assert response.status_code==422 and not calls
    assert 'private-marker' not in response.text

def test_missing_readback_is_not_saved(setup,monkeypatch):
    client,_=setup
    monkeypatch.setattr(robustness_saves,'database',lambda *a,**k:[])
    assert client.post('/api/v1/robustness/runs',json=body()).status_code==503
    assert client.get('/api/v1/robustness/runs/'+run()['experiment_id']).status_code==404
