"""Real project tests. Skip unless two locally configured confirmed users exist.

No fake users/tokens; never print HTTP bodies or credentials. Creates and removes
uniquely named test metadata through each user's own session and RLS.
"""
import json
import os
import re
import base64
from uuid import uuid4
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from app.core.config import BACKEND_ROOT, Settings
from app.main import create_app


def _live_accounts(labels):
    if os.getenv('WATERMARKLAB_SAFE_HOSTED_RUNNER') != '1':
        pytest.skip('Use scripts/run_hosted_tests.py to prevent credential-bearing failure output')
    if os.getenv('WATERMARKLAB_LIVE_TESTS') != '1':
        pytest.skip('Hosted integration pending; explicitly opt in only after migration approval/execution')
    config = dotenv_values(BACKEND_ROOT / '.env.integration')
    required = [f'TEST_USER_{label}_{field}' for label in labels for field in ('EMAIL', 'PASSWORD')]
    if not all(config.get(key) for key in required):
        pytest.skip('Required confirmed local integration accounts not configured')
    settings = Settings()
    def call(path, token=None, method='GET', body=None):
        headers = {'apikey': settings.supabase_publishable_key.get_secret_value(), 'Content-Type': 'application/json', 'Prefer': 'return=representation'}
        if token: headers['Authorization'] = 'Bearer ' + token
        request = Request(settings.supabase_url + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except HTTPError as error:
            try:
                code = json.loads(error.read()).get('code', '')
            except (ValueError, AttributeError):
                code = ''
            call.last_error_code = code if isinstance(code,str) and re.fullmatch(r'[A-Z0-9]{5,10}',code) else 'UNKNOWN'
            return error.code, None
    accounts = []
    for label in labels:
        status, result = call('/auth/v1/token?grant_type=password', method='POST', body={'email':config[f'TEST_USER_{label}_EMAIL'], 'password':config[f'TEST_USER_{label}_PASSWORD']})
        assert status == 200, 'Real sign-in failed; check confirmed test accounts locally'
        assert result['user'].get('email_confirmed_at'), 'Integration account email is not confirmed'
        accounts.append((result['user']['id'], result['access_token']))
    assert len({uid for uid, _ in accounts}) == len(accounts), 'Test accounts must be independent'
    try:
        yield settings, call, accounts
    finally:
        for _, token in accounts:
            call('/auth/v1/logout?scope=local', token, 'POST')


@pytest.fixture(scope='module')
def live():
    yield from _live_accounts(('A', 'B'))


@pytest.fixture(scope='module')
def live_a():
    yield from _live_accounts(('A',))


@pytest.fixture
def owned(live):
    _, call, accounts = live
    owner, token = accounts[0]
    status, rows = call('/rest/v1/experiments', token, 'POST', {'user_id':owner, 'title':'Integration ' + str(uuid4())})
    assert status == 201, 'Migration/grants/INSERT policy not ready'
    row = rows[0]
    yield call, accounts, row
    call('/rest/v1/experiments?id=eq.' + row['id'], token, 'DELETE')


def test_live_backend_signature_and_user_identity(live):
    settings, _, accounts = live
    client = TestClient(create_app(settings))
    for user_id, token in accounts:
        response = client.get('/api/v1/me', headers={'Authorization':'Bearer ' + token})
        assert response.status_code == 200
        assert response.json() == {'id':user_id}
        parts=token.split('.')
        payload=json.loads(base64.urlsafe_b64decode(parts[1]+'='*((-len(parts[1]))%4)))
        payload['sub']=str(uuid4())
        parts[1]=base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        forged='.'.join(parts)
        assert client.get('/api/v1/me',headers={'Authorization':'Bearer '+forged}).status_code==401


def test_live_select_isolation(owned):
    call, accounts, row = owned
    path = '/rest/v1/experiments?id=eq.' + row['id']
    assert call(path, accounts[0][1])[1][0]['id'] == row['id']
    assert call(path, accounts[1][1]) == (200, [])
    assert call(path)[0] in (401,403)


def test_live_insert_policy(owned):
    call, accounts, _ = owned
    assert call('/rest/v1/experiments',accounts[1][1],'POST',{'user_id':accounts[0][0],'title':'forbidden'})[0] in (401,403)


def test_live_update_policy(owned):
    call, accounts, row = owned
    path = '/rest/v1/experiments?id=eq.' + row['id']
    assert call(path,accounts[1][1],'PATCH',{'title':'forbidden'}) == (200,[])
    assert call(path,accounts[0][1],'PATCH',{'user_id':accounts[1][0]})[0] in (401,403)
    assert call(path,accounts[0][1],'PATCH',{'title':'updated'})[1][0]['title']=='updated'


def test_live_delete_policy(owned):
    call, accounts, row = owned
    path = '/rest/v1/experiments?id=eq.' + row['id']
    assert call(path,accounts[1][1],'DELETE') == (200,[])
    assert call(path,accounts[0][1])[1][0]['id']==row['id']
    assert call(path,accounts[0][1],'DELETE')[1][0]['id']==row['id']


@pytest.fixture(params=['profiles','experiment_samples'])
def owned_child(request, live):
    _, call, accounts = live
    owner, token = accounts[0]
    table=request.param
    original=None
    parent=None
    if table=='profiles':
        status, rows=call('/rest/v1/profiles?id=eq.'+owner,token)
        assert status==200, 'Profile migration/grants unavailable'
        original=rows[0] if rows else None
        if not original:
            assert call('/rest/v1/profiles',token,'POST',{'id':owner,'display_name':'Integration test'})[0]==201
        row={'id':owner}
    else:
        status, rows=call('/rest/v1/experiments',token,'POST',{'user_id':owner,'title':'Child isolation test'})
        assert status==201, 'Migration/grants unavailable'
        parent=rows[0]['id']
        status, rows=call('/rest/v1/experiment_samples',token,'POST',{'user_id':owner,'experiment_id':parent})
        assert status==201
        row=rows[0]
    yield call,accounts,table,row
    if parent: call('/rest/v1/experiments?id=eq.'+parent,token,'DELETE')
    elif original:
        call('/rest/v1/profiles?id=eq.'+owner,token,'DELETE')
        call('/rest/v1/profiles',token,'POST',original)
    else: call('/rest/v1/profiles?id=eq.'+owner,token,'DELETE')


def test_live_child_select(owned_child):
    call,accounts,table,row=owned_child
    path=f'/rest/v1/{table}?id=eq.'+row['id']
    assert call(path,accounts[0][1])[1][0]['id']==row['id']
    assert call(path,accounts[1][1])==(200,[])
    assert call(path)[0] in (401,403)


def test_live_child_insert(owned_child):
    call,accounts,table,row=owned_child
    payload={k:v for k,v in row.items() if k!='created_at'}
    if table!='profiles': payload['id']=str(uuid4())
    # Insert a row claiming A's ownership through B's independently signed session.
    assert call(f'/rest/v1/{table}',accounts[1][1],'POST',payload)[0] in (401,403)


def test_live_child_update(owned_child):
    call,accounts,table,row=owned_child
    path=f'/rest/v1/{table}?id=eq.'+row['id']
    field='display_name' if table=='profiles' else 'provenance_label' if table=='experiment_samples' else 'verdict'
    value='Integration updated' if table=='profiles' else 'UNKNOWN' if table=='experiment_samples' else 'INCONCLUSIVE'
    assert call(path,accounts[1][1],'PATCH',{field:value})==(200,[])
    owner_field='id' if table=='profiles' else 'user_id'
    denied_status=call(path,accounts[0][1],'PATCH',{owner_field:accounts[1][0]})[0]
    # Immutable sample identity is checked by the BEFORE trigger (23514), before RLS WITH CHECK.
    assert denied_status in (401,403) or (table=='experiment_samples' and denied_status==400 and call.last_error_code=='23514'), f'DENIAL_STATUS={denied_status};CODE={call.last_error_code}'
    assert call(path,accounts[0][1],'PATCH',{field:value})[1][0][field]==value


def test_live_child_delete(owned_child):
    call,accounts,table,row=owned_child
    path=f'/rest/v1/{table}?id=eq.'+row['id']
    assert call(path,accounts[1][1],'DELETE')==(200,[])
    assert call(path,accounts[0][1])[1][0]['id']==row['id']
    assert call(path,accounts[0][1],'DELETE')[1][0]['id']==row['id']


@pytest.mark.parametrize('operation', ['POST','PATCH','DELETE'])
def test_live_detection_writes_denied(owned, operation):
    call,accounts,row=owned
    path='/rest/v1/detection_results' + ('' if operation=='POST' else '?id=eq.'+str(uuid4()))
    body={'user_id':accounts[0][0],'experiment_id':row['id'],'sample_id':str(uuid4()),'detector_method':'KGW','verdict':'UNAVAILABLE'} if operation=='POST' else {'verdict':'DETECTED'} if operation=='PATCH' else None
    for _,token in accounts:
        denied_status=call(path,token,operation,body)[0]
        assert denied_status in (401,403), f'DENIAL_STATUS={denied_status};CODE={call.last_error_code}'


def test_live_api_experiment_ownership_and_validation(live):
    settings,_,accounts=live
    client=TestClient(create_app(settings))
    a={'Authorization':'Bearer '+accounts[0][1]}
    b={'Authorization':'Bearer '+accounts[1][1]}
    response=client.post('/api/v1/experiments',headers=a,json={'title':'API integration '+str(uuid4())})
    assert response.status_code==201
    row_id=response.json()['id']
    try:
        response=client.get('/api/v1/experiments',headers=b)
        assert response.status_code==200
        assert row_id not in [row['id'] for row in response.json()]
        assert client.patch('/api/v1/experiments/'+row_id,headers=b,json={'title':'forbidden'}).status_code==404
        assert client.delete('/api/v1/experiments/'+row_id,headers=b).status_code==404
        assert client.post('/api/v1/experiments',headers=b,json={'title':'forbidden','user_id':accounts[0][0]}).status_code==422
        assert client.patch('/api/v1/experiments/'+row_id,headers=a,json={'title':'updated by owner'}).status_code==200
    finally:
        assert client.delete('/api/v1/experiments/'+row_id,headers=a).status_code==204


def test_live_api_profile_upsert_with_both_accounts(live):
    settings,call,accounts=live
    client=TestClient(create_app(settings))
    for user_id,token in accounts:
        headers={'Authorization':'Bearer '+token}
        original=client.get('/api/v1/profile',headers=headers)
        assert original.status_code==200
        original=original.json()
        try:
            response=client.put('/api/v1/profile',headers=headers,json={'display_name':'API profile test','retain_text':False})
            assert response.status_code==200
            assert response.json()['id']==user_id
            assert client.get('/api/v1/profile',headers=headers).json()['display_name']=='API profile test'
            assert client.put('/api/v1/profile',headers=headers,json={'display_name':'forbidden','id':str(uuid4())}).status_code==422
        finally:
            if original:
                assert client.put('/api/v1/profile',headers=headers,json={'display_name':original['display_name'],'retain_text':original['retain_text']}).status_code==200
            else:
                assert call('/rest/v1/profiles?id=eq.'+user_id,token,'DELETE')[0]==200


def test_live_refresh_then_logout_invalidates_refresh(live):
    settings,call,_=live
    config=dotenv_values(BACKEND_ROOT/'.env.integration')
    client=TestClient(create_app(settings))
    for label in ['A','B']:
        status,session=call('/auth/v1/token?grant_type=password',method='POST',body={'email':config[f'TEST_USER_{label}_EMAIL'],'password':config[f'TEST_USER_{label}_PASSWORD']})
        assert status==200
        try:
            status,refreshed=call('/auth/v1/token?grant_type=refresh_token',method='POST',body={'refresh_token':session['refresh_token']})
            assert status==200
            session=refreshed
            assert client.get('/api/v1/me',headers={'Authorization':'Bearer '+session['access_token']}).status_code==200
        finally:
            assert call('/auth/v1/logout?scope=local',session['access_token'],'POST')[0] in (200,204)
        assert call('/auth/v1/token?grant_type=refresh_token',method='POST',body={'refresh_token':session['refresh_token']})[0] in (400,401,403,422)


def test_live_retention_both_gates_and_opt_out_purge(live,owned):
    settings,call,accounts=live
    _,_,experiment=owned
    user_id,token=accounts[0]
    client=TestClient(create_app(settings))
    headers={'Authorization':'Bearer '+token}
    response=client.get('/api/v1/profile',headers=headers)
    assert response.status_code==200
    original=response.json()
    try:
        assert client.put('/api/v1/profile',headers=headers,json={'display_name':'Retention integration test','retain_text':False}).status_code==200
        status,rows=call('/rest/v1/experiment_samples',token,'POST',{'user_id':user_id,'experiment_id':experiment['id']})
        assert status==201
        path='/rest/v1/experiment_samples?id=eq.'+rows[0]['id']
        assert call(path,token,'PATCH',{'raw_text':'Synthetic retention fixture','retention_consent':True})[0]==400
        assert call.last_error_code=='23514'
        assert client.put('/api/v1/profile',headers=headers,json={'display_name':'Retention integration test','retain_text':True}).status_code==200
        assert call(path,token,'PATCH',{'raw_text':'Synthetic retention fixture','retention_consent':False})[0]==400
        assert call.last_error_code=='23514'
        assert call(path,token,'PATCH',{'raw_text':'Synthetic retention fixture','retention_consent':True})[0]==200
        assert client.put('/api/v1/profile',headers=headers,json={'display_name':'Retention integration test','retain_text':False}).status_code==200
        status,rows=call(path,token)
        assert status==200 and rows[0]['raw_text'] is None and not rows[0]['retention_consent']
        assert call(path,accounts[1][1])==(200,[])
    finally:
        if original:
            assert client.put('/api/v1/profile',headers=headers,json={'display_name':original['display_name'],'retain_text':original['retain_text']}).status_code==200
        else:
            assert call('/rest/v1/profiles?id=eq.'+user_id,token,'DELETE')[0]==200
