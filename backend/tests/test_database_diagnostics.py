"""All upstream errors are synthetic; no external requests or real credentials."""
import io
import json
from urllib.error import HTTPError
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.core.security import Identity,require_user
from app.core.database_diagnostics import HEADER,LIMIT,parse_http_error
from app.api.routes import accounts
from test_run_receipts import run,OWNER,KEY
from app.services.run_receipts import issue

def error(body,status=400):
    return HTTPError('https://invalid.example',status,'private-marker',{},io.BytesIO(body))

@pytest.mark.parametrize('body,expected',[
 (b'{"code":"23514","message":"private-marker","details":"private-marker","hint":"private-marker"}','23514'),
 (b'{"code":"PGRST202"}','PGRST202'),
 (b'{"code":"SECRET"}',None),(b'{"code":[]}',None),
 (b'not json private-marker',None),(b'[]',None),
 (b'{"code":"23514","message":"'+b'x'*LIMIT+b'"}',None),
])
def test_bounded_parser(body,expected):
    e=error(body);result=parse_http_error(e,'save_rpc')
    assert result['postgrest_code']==expected
    assert result['sqlstate']==(expected if expected and len(expected)==5 else None)
    assert result['upstream_http_status']==400
    assert e.fp.tell()<=LIMIT+1
    assert 'private-marker' not in json.dumps(result)

def client(monkeypatch,stage='save_rpc',status=400,env='development',enabled=True,host='127.0.0.1',success=False):
    settings=Settings(_env_file=None,supabase_url='https://invalid.example',supabase_publishable_key='sb_publishable_dummy',robustness_signing_key=KEY,database_diagnostics_enabled=enabled)
    settings=settings.model_copy(update={'app_env':env})
    app=create_app(settings);app.dependency_overrides[require_user]=lambda:Identity(OWNER,'dummy-token')
    calls=[]
    def urlopen(request,timeout):
        calls.append(request.method)
        if success or (stage=='readback' and len(calls)==1):
            return io.BytesIO(json.dumps([{'experiment_id':run()['experiment_id']}]).encode())
        raise error(json.dumps({'code':'42501' if status==403 else '23514','message':'private-marker','details':'private-marker','hint':'private-marker'}).encode(),status)
    monkeypatch.setattr(accounts,'urlopen',urlopen)
    return TestClient(app,client=(host,12345))

@pytest.mark.parametrize('stage',['save_rpc','readback'])
@pytest.mark.parametrize('status',[400,403])
def test_exact_internal_stage_and_outer_status(monkeypatch,stage,status):
    with client(monkeypatch,stage,status) as c:
        r=c.post('/api/v1/robustness/runs',json={**issue(run(),OWNER,KEY),'save_consent':True},headers={'X-WatermarkLab-Diagnostics':'1'})
    assert r.status_code==(403 if status==403 else 503)
    assert r.json()=={'detail':'Database access denied' if status==403 else 'Database request failed. Check migration and grants.'}
    diagnostic=json.loads(r.headers[HEADER]);assert diagnostic['database_stage']==stage
    assert diagnostic['upstream_http_status']==status
    assert diagnostic['rpc_function']==('save_robustness_run' if stage=='save_rpc' else None)
    assert 'private-marker' not in r.text+str(r.headers)

@pytest.mark.parametrize('env,enabled,host,headers',[
 ('production',True,'127.0.0.1',{'X-WatermarkLab-Diagnostics':'1'}),
 ('test',True,'127.0.0.1',{'X-WatermarkLab-Diagnostics':'1'}),
 ('development',False,'127.0.0.1',{'X-WatermarkLab-Diagnostics':'1'}),
 ('development',True,'192.0.2.1',{'X-WatermarkLab-Diagnostics':'1'}),
 ('development',True,'127.0.0.1',{}),
 ('development',True,'127.0.0.1',{'X-WatermarkLab-Diagnostics':'1','Origin':'http://localhost:5173'}),
])
def test_diagnostics_unavailable_outside_explicit_local_development(monkeypatch,env,enabled,host,headers):
    with client(monkeypatch,env=env,enabled=enabled,host=host) as c:
        r=c.post('/api/v1/robustness/runs',json={**issue(run(),OWNER,KEY),'save_consent':True},headers=headers)
    assert r.status_code==503 and HEADER not in r.headers
    assert r.json()=={'detail':'Database request failed. Check migration and grants.'}

def test_success_has_no_failure_diagnostic(monkeypatch):
    with client(monkeypatch,success=True) as c:
        r=c.post('/api/v1/robustness/runs',json={**issue(run(),OWNER,KEY),'save_consent':True},headers={'X-WatermarkLab-Diagnostics':'1'})
    assert r.status_code==200 and r.json()['status']=='saved' and HEADER not in r.headers

def test_receipt_failure_does_not_claim_database_stage(monkeypatch):
    with client(monkeypatch) as c:
        r=c.post('/api/v1/robustness/runs',json={**issue(run(),OWNER,KEY),'signature':'0'*64,'save_consent':True},headers={'X-WatermarkLab-Diagnostics':'1'})
    assert r.status_code==422 and HEADER not in r.headers
