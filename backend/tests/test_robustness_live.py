"""Opt-in hosted Phase 7 workflow; safe fixed-label report, no raw HTTP output."""
import json
import os
from uuid import UUID, uuid4
import httpx
import pytest
from dotenv import dotenv_values
from app.core.config import BACKEND_ROOT, Settings
from test_supabase_live import live, live_a
from scripts.hosted_diagnostics import response_diagnostic, sanitize

@pytest.fixture(scope='module',autouse=True)
def optin():
    if any(os.getenv(k)!='1' for k in ('WATERMARKLAB_LIVE_TESTS','WATERMARKLAB_PHASE7_PERSISTENCE_TESTS','WATERMARKLAB_SAFE_HOSTED_RUNNER')):
        pytest.skip('Explicit safe runner and Phase 7 hosted opt-ins required')
    frontend={}
    for name in ('.env','.env.local','.env.development','.env.development.local'):
        path=BACKEND_ROOT.parent/'frontend'/name
        if path.exists():frontend.update(dotenv_values(path))
    frontend.update({k:v for k,v in os.environ.items() if k.startswith('VITE_')})
    settings=Settings()
    assert frontend.get('VITE_SUPABASE_URL','').rstrip('/')==settings.supabase_url
    assert settings.supabase_publishable_key.get_secret_value().startswith('sb_publishable_')
    assert settings.robustness_signing_key.get_secret_value()
    assert settings.robustness_signing_key_id=='v1'

def test_hosted_robustness_save_diagnostic_only(live_a, request):
    """One comparison/save only; select this exact node through the safe runner."""
    _, db, accounts = live_a
    assert len(accounts) == 1, 'Diagnostic requires Account A only'
    owner, token = accounts[0]
    report = {'cases': {}, 'comparison_requests': 0, 'save_requests': 0,
              'gemini_requests': 0, 'cleanup': {'status': 'not_required', 'own_experiment_absent': None}}
    output = BACKEND_ROOT / '.cache/phase7_save_diagnostic_results.json'
    output.parent.mkdir(exist_ok=True)

    def persist():
        output.write_text(json.dumps(report, indent=2))

    def check(name, condition):
        report['cases'][name] = 'passed' if condition else 'failed'
        persist()
        assert condition, name

    identifier = None
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=120, trust_env=False) as api:
        def req(method, path, stage, body=None):
            try:
                response = api.request(method, '/api/v1/' + path, headers={
                    'Authorization': 'Bearer ' + token, 'X-WatermarkLab-Diagnostics': '1'}, json=body)
            except Exception:
                diagnostic = sanitize({'request_stage': stage, 'application_code': 'request_failed'})
                report.setdefault('http_diagnostics', []).append(diagnostic)
                request.node.user_properties.append(('safe_http_diagnostic', diagnostic))
                persist()
                raise AssertionError('Diagnostic request failed; raw details suppressed') from None
            diagnostic = response_diagnostic(response, stage)
            report.setdefault('http_diagnostics', []).append(diagnostic)
            request.node.user_properties.append(('safe_http_diagnostic', diagnostic))
            persist()
            return response

        try:
            response = req('GET', 'me', 'identity')
            check('identity_A', response.status_code == 200 and response.json().get('id') == owner)
            response = req('GET', 'profile', 'profile')
            check('profile_exists', response.status_code == 200 and bool(response.json()))
            status, data = db('/rest/v1/experiment_samples?raw_text=not.is.null&select=id&limit=1', token)
            check('no_preexisting_retained_text_at_risk', status == 200 and data == [])
            samples = json.loads((BACKEND_ROOT / 'research/kgw_pilot.json').read_text())['samples']
            text = next(s['text'] for s in samples if s['provenance'] == 'KNOWN_WATERMARKED') + ' Synthetic QA run ' + str(uuid4())
            report['comparison_requests'] += 1
            # /compare currently never persists. Still refuse to certify cleanup
            # if its response/ID is lost; never guess an ID or search owner rows.
            report['cleanup']['status'] = 'unverified'
            response = req('POST', 'compare', 'compare', {
                'text': text, 'method': 'KGW', 'profile_id': 'kgw-gpt2-cpu-v1',
                'compatibility_confirmed': True, 'operation': 'shorten', 'strength': 25})
            check('real_comparison', response.status_code == 200)
            try:
                run = response.json()
                candidate = run.get('experiment_id') if isinstance(run, dict) else None
                parsed = UUID(candidate) if isinstance(candidate, str) else None
                valid_id = parsed is not None and parsed.version == 4 and str(parsed) == candidate
            except (ValueError, TypeError, AttributeError):
                valid_id = False
            check('recoverable_comparison_id', valid_id)
            identifier = candidate
            check('signed_receipt', bool(run.get('receipt')))
            report['save_requests'] += 1
            response = req('POST', 'robustness/runs', 'save_endpoint', {
                **run['receipt'], 'save_consent': True, 'retain_text': False,
                'original_text': None, 'child_text': None})
            check('owner_metadata_save', response.status_code == 200 and response.json().get('status') == 'saved')
        finally:
            if identifier is not None:
                try:
                    response = req('DELETE', 'experiments/' + identifier, 'cleanup')
                    status, data = db('/rest/v1/experiments?id=eq.' + identifier, token)
                    report['cleanup']['own_experiment_absent'] = response.status_code in (204, 404) and status == 200 and data == []
                except Exception:
                    report['cleanup']['own_experiment_absent'] = False
                report['cleanup']['status'] = 'verified' if report['cleanup']['own_experiment_absent'] else 'failed'
            persist()
            assert report['comparison_requests'] == 0 or report['cleanup']['own_experiment_absent'] is True, 'Diagnostic cleanup failed or unverified'


def test_hosted_robustness_persistence(live,request):
    _,db,accounts=live
    owner,a=accounts[0];_,b=accounts[1]
    report={'cases':{},'comparison_requests':0,'gemini_requests':0,'cleanup':{},'profile_restored':False}
    output=BACKEND_ROOT/'.cache/phase7_hosted_results.json';output.parent.mkdir(exist_ok=True)
    def persist():output.write_text(json.dumps(report,indent=2))
    def check(name,condition):
        report['cases'][name]='passed' if condition else 'failed';persist()
        assert condition, name
    created=[];original=None;changed=False
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=120,trust_env=False) as api:
        def req(method,path,token=a,body=None):
            stage='save_endpoint' if path=='robustness/runs' else 'compare' if path=='compare' else 'readback' if path.startswith('robustness/runs/') else 'profile' if path=='profile' else 'identity' if path=='me' else 'cleanup'
            try:
                response=api.request(method,'/api/v1/'+path,headers={'Authorization':'Bearer '+token,'X-WatermarkLab-Diagnostics':'1'},json=body)
            except Exception:
                diagnostic=sanitize({'request_stage':stage,'application_code':'request_failed','rpc_function':None})
                report.setdefault('http_diagnostics',[]).append(diagnostic)
                request.node.user_properties.append(('safe_http_diagnostic',diagnostic))
                persist()
                raise
            diagnostic=response_diagnostic(response,stage)
            report.setdefault('http_diagnostics',[]).append(diagnostic)
            request.node.user_properties.append(('safe_http_diagnostic',diagnostic))
            persist()
            return response
        def rows(table,identifier,token=a):
            status,data=db('/rest/v1/'+table+'?experiment_id=eq.'+identifier,token)
            check('read_'+table+'_'+('A' if token==a else 'B'),status==200)
            return data
        def preference(value):
            nonlocal changed
            changed=True
            check('profile_update',req('PUT','profile',body={'display_name':original['display_name'],'retain_text':value}).status_code==200)
        def compare():
            fixtures=json.loads((BACKEND_ROOT/'research/kgw_pilot.json').read_text())['samples']
            text=next(s['text'] for s in fixtures if s['provenance']=='KNOWN_WATERMARKED')+' Synthetic QA run '+str(uuid4())
            report['comparison_requests']+=1
            response=req('POST','compare',body={'text':text,'method':'KGW','profile_id':'kgw-gpt2-cpu-v1','compatibility_confirmed':True,'operation':'shorten','strength':25})
            check('real_comparison',response.status_code==200)
            run=response.json();check('signed_receipt',bool(run.get('receipt')))
            created.append(run['experiment_id'])
            return run
        def payload(run,retain=False):
            return {**run['receipt'],'save_consent':True,'retain_text':retain,'original_text':run['original']['text'] if retain else None,'child_text':run['child']['text'] if retain else None}
        try:
            for uid,token in accounts:
                response=req('GET','me',token)
                check('identity_'+('A' if token==a else 'B'),response.status_code==200 and response.json().get('id')==uid)
            response=req('GET','profile');check('profile_read',response.status_code==200)
            original=response.json();check('profile_exists',bool(original))
            # Opt-out purges all user texts: refuse before mutation if existing data could be affected.
            status,data=db('/rest/v1/experiment_samples?raw_text=not.is.null&select=id&limit=1',a)
            check('no_preexisting_retained_text_at_risk',status==200 and data==[])
            run=compare();identifier=run['experiment_id'];body=payload(run)
            response=req('POST','robustness/runs',body=body)
            check('owner_save',response.status_code==200 and response.json().get('status')=='saved')
            check('owner_readback',req('GET','robustness/runs/'+identifier).status_code==200)
            check('B_readback_404',req('GET','robustness/runs/'+identifier,b).status_code==404)
            check('B_receipt_rejected',req('POST','robustness/runs',b,body).status_code in (401,403,422))
            samples=rows('experiment_samples',identifier)
            check('metadata_only_no_text',len(samples)==2 and all(s['raw_text'] is None and not s['retention_consent'] for s in samples))
            check('identical_retry',req('POST','robustness/runs',body=body).status_code==200)
            check('no_duplicate_rows',len(rows('experiment_samples',identifier))==2 and len(rows('detection_results',identifier))==2 and len(rows('robustness_runs',identifier))==1)
            for table in ('experiment_samples','detection_results'):
                check('B_isolation_'+table,rows(table,identifier,b)==[])
            for table,data in [('robustness_runs',{'experiment_id':identifier,'user_id':owner}),('detection_results',{'user_id':owner,'experiment_id':identifier,'sample_id':samples[0]['id'],'detector_method':'KGW','verdict':'UNAVAILABLE'})]:
                check('direct_insert_denied_'+table,db('/rest/v1/'+table,a,'POST',data)[0] in (401,403))
            preference(False)
            retained=compare();retained_body=payload(retained,True)
            check('retention_without_profile_rejected',req('POST','robustness/runs',body=retained_body).status_code in (400,403,422,503))
            check('failed_save_atomic',rows('robustness_runs',retained['experiment_id'])==[])
            preference(True)
            check('same_receipt_recovery',req('POST','robustness/runs',body=retained_body).status_code==200)
            saved=rows('experiment_samples',retained['experiment_id'])
            check('both_texts_retained',len(saved)==2 and {s['raw_text'] for s in saved}=={retained['original']['text'],retained['child']['text']} and all(s['retention_consent'] for s in saved))
            preference(False)
            saved=rows('experiment_samples',retained['experiment_id'])
            check('optout_purges_text_and_consent',len(saved)==2 and all(s['raw_text'] is None and not s['retention_consent'] for s in saved))
            check('retry_does_not_restore',req('POST','robustness/runs',body=retained_body).status_code==200 and all(s['raw_text'] is None for s in rows('experiment_samples',retained['experiment_id'])))
            check('owner_delete',req('DELETE','experiments/'+identifier).status_code==204)
            check('deleted_receipt_replay_rejected',req('POST','robustness/runs',body=body).status_code in (400,403,422,503))
            check('deleted_run_absent',req('GET','robustness/runs/'+identifier).status_code==404 and rows('robustness_runs',identifier)==[])
        finally:
            for i,identifier in enumerate(created):
                try:
                    response=req('DELETE','experiments/'+identifier)
                    status,data=db('/rest/v1/experiments?id=eq.'+identifier,a)
                    report['cleanup'][str(i)]=response.status_code in (204,404) and status==200 and data==[]
                except Exception:report['cleanup'][str(i)]=False
            if original:
                try:
                    if changed:req('PUT','profile',body={'display_name':original['display_name'],'retain_text':original['retain_text']})
                    restored=req('GET','profile')
                    report['profile_restored']=restored.status_code==200 and restored.json()==original
                except Exception:report['profile_restored']=False
            persist()
            assert all(report['cleanup'].values()) and (report['profile_restored'] or original is None), 'Cleanup or restoration failed'
