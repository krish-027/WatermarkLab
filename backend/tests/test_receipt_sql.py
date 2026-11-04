"""Isolated PostgreSQL only. Public dummy signing key, never hosted secrets."""
import json
from pathlib import Path
from uuid import uuid4
import pytest
from test_migration_local import sql, A, B, ROOT
from test_run_receipts import run,KEY
from app.services.run_receipts import issue

@pytest.fixture(scope='module')
def writer(sql):
    # Supabase-style public-object defaults for the actual local creating role.
    sql('create role service_role nologin bypassrls; grant usage on schema public to service_role; alter default privileges in schema public grant all on tables to service_role; alter default privileges in schema public grant execute on functions to service_role')
    sql('create table public.default_acl_probe(id integer); create function public.default_acl_probe() returns integer language sql as $$ select 1 $$')
    assert sql("select has_table_privilege('service_role','public.default_acl_probe','SELECT'),has_function_privilege('service_role','public.default_acl_probe()','EXECUTE')")[0]=='t|t'
    sql('drop table public.default_acl_probe; drop function public.default_acl_probe()')
    # Global defaults apply to the private schema and its future sensitive tables.
    sql('alter default privileges grant all on schemas to service_role; alter default privileges grant all on tables to service_role; create schema private_acl_probe; create table private_acl_probe.receipt_keys(id integer); create table private_acl_probe.receipt_consumptions(id integer)')
    assert sql("select has_schema_privilege('service_role','private_acl_probe','USAGE'),has_schema_privilege('service_role','private_acl_probe','CREATE'),has_table_privilege('service_role','private_acl_probe.receipt_keys','SELECT'),has_table_privilege('service_role','private_acl_probe.receipt_consumptions','MAINTAIN')")[0]=='t|t|t|t'
    sql('drop schema private_acl_probe cascade')
    sql((ROOT/'supabase/migrations/202610310001_robustness_receipts.sql').read_text())
    catalog = "select proowner,proacl,prosecdef,proconfig from pg_proc where oid='public.save_robustness_run(text,text,text,text,text,boolean,jsonb)'::regprocedure"
    before = sql(catalog)[0]
    sql((ROOT/'supabase/migrations/202611040002_writer_jwt_subject.sql').read_text())
    assert sql(catalog)[0] == before
    # Model the hosted restriction throughout all receipt/retention/replay tests.
    sql('revoke usage on schema auth from watermarklab_run_writer')
    sql("insert into watermarklab_private.receipt_keys values ('v1',decode('"+KEY+"','hex'),true)")
    return sql

def receipt():
    value=run();value['experiment_id']=str(uuid4())
    value['original']['id']=str(uuid4());value['child']['id']=str(uuid4())
    value['child']['parent_sample_id']=value['original']['id']
    return issue(value,A,KEY)

def test_catalog_audit(writer):
    assert 'Robustness catalog audit passed' in writer((ROOT/'supabase/tests/robustness_grants_audit.sql').read_text())[0]

@pytest.mark.parametrize('privilege',['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN'])
def test_service_role_default_table_grants_removed(writer,privilege):
    assert writer("select has_table_privilege('service_role','public.robustness_runs','"+privilege+"')")[0]=='f'

def test_service_role_execution_and_manifest_access_denied(writer):
    writer('select * from public.robustness_runs',A,role='service_role',succeeds=False)
    writer(call(receipt()),A,role='service_role',succeeds=False)
    for fn in ['public.protect_robustness_sample()','public.save_robustness_run(text,text,text,text,text,boolean,jsonb)']:
        assert writer("select has_function_privilege('service_role','"+fn+"','EXECUTE')")[0]=='f'

@pytest.mark.parametrize('privilege',['USAGE','CREATE'])
def test_service_role_private_schema_defaults_removed(writer,privilege):
    assert writer("select has_schema_privilege('service_role','watermarklab_private','"+privilege+"')")[0]=='f'

@pytest.mark.parametrize('table',['receipt_keys','receipt_consumptions'])
@pytest.mark.parametrize('privilege',['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN'])
def test_service_role_private_table_defaults_removed(writer,table,privilege):
    assert writer("select has_table_privilege('service_role','watermarklab_private."+table+"','"+privilege+"')")[0]=='f'

def test_service_role_private_access_denied(writer):
    for table in ['receipt_keys','receipt_consumptions']:
        writer('select * from watermarklab_private.'+table,A,role='service_role',succeeds=False)
    writer('create table watermarklab_private.forbidden_service_object(id integer)',A,role='service_role',succeeds=False)

def test_non_superuser_ownership_transfer_and_revocation(writer):
    # Model Supabase's admin-only membership; postgres is NOT local superuser.
    writer('create role transfer_owner nologin noinherit nobypassrls; grant transfer_owner to postgres with admin true, set false, inherit false; grant usage,create on schema public to postgres with grant option')
    writer('create function public.transfer_probe() returns integer language sql as $$ select 1 $$',login='postgres')
    writer('alter function public.transfer_probe() owner to transfer_owner',login='postgres',succeeds=False)
    writer('grant create on schema public to transfer_owner; grant transfer_owner to postgres with set true, inherit false; alter function public.transfer_probe() owner to transfer_owner; revoke transfer_owner from postgres; revoke create on schema public from transfer_owner',login='postgres')
    assert writer("select pg_has_role('postgres','transfer_owner','SET'),has_schema_privilege('transfer_owner','public','CREATE')")[0]=='f|f'
    writer('set role transfer_owner',login='postgres',succeeds=False)
    assert writer("select pg_has_role('postgres','watermarklab_run_writer','SET'),has_schema_privilege('watermarklab_run_writer','public','CREATE')")[0]=='f|f'
    writer('set role watermarklab_run_writer',login='postgres',succeeds=False)
    writer('drop function public.transfer_probe(); revoke create,usage on schema public from postgres; drop owned by transfer_owner; drop role transfer_owner')

@pytest.mark.parametrize('method',['KGW','SYNTHID'])
def test_unavailable_child_and_native_evidence(writer,method):
    value=run();value['experiment_id']=str(uuid4())
    value['original']['id']=str(uuid4());value['child']['id']=str(uuid4())
    value['child']['parent_sample_id']=value['original']['id']
    before=dict(value['original']['detection'])
    if method=='SYNTHID':before.update(method=method,profile_id='synthid-threefry-gpt2-cpu-v1',z_score=None,p_value=0.001,threshold=0.01)
    value['original']['detection']=before
    value['child']['detection']={**before,'verdict':'UNAVAILABLE','z_score':None,'p_value':None,'threshold':None}
    r=issue(value,A,KEY)
    assert writer(call(r),A)[0]==value['experiment_id']

def call(r,extra=''):
    quote=lambda s:"'"+s.replace("'","''")+"'"
    return 'select public.save_robustness_run('+','.join(quote(r[k]) for k in ('payload','signature','key_id'))+extra+')'

def test_atomic_metadata_save_replay_and_isolation(writer):
    r=receipt();identifier=json.loads(r['payload'])['id']
    assert writer(call(r),A)[0]==identifier
    assert writer(call(r),A)[0]==identifier
    assert writer("select count(*) from public.robustness_runs where experiment_id='"+identifier+"'",B)[0]=='0'
    writer(call(r),B,succeeds=False)
    assert writer("select count(*) from public.detection_results where experiment_id='"+identifier+"'",A)[0]=='2'
    assert writer("select count(*) from public.experiment_samples where experiment_id='"+identifier+"' and raw_text is not null",A)[0]=='0'

def test_forged_receipt_cannot_insert(writer):
    r=receipt();r['signature']='0'*64
    writer(call(r),A,succeeds=False)

def test_direct_result_insert_still_denied(writer):
    writer("insert into public.detection_results(user_id,experiment_id,sample_id,detector_method,verdict) values('"+A+"',gen_random_uuid(),gen_random_uuid(),'KGW','DETECTED')",A,succeeds=False)
    writer('select * from watermarklab_private.receipt_keys',A,succeeds=False)

def test_retention_requires_profile_and_text_commitments(writer):
    r=receipt();identifier=json.loads(r['payload'])['id']
    writer(call(r,",'private original','private child',true"),A,succeeds=False)
    assert writer("select count(*) from public.experiments where id='"+identifier+"'",A)[0]=='0'
    writer("insert into public.profiles(id,retain_text) values('"+A+"',true) on conflict(id) do update set retain_text=true",A)
    writer(call(r,",'tampered','private child',true"),A,succeeds=False)
    writer(call(r,",'private original','private child',true"),A)
    writer("update public.profiles set retain_text=false where id='"+A+"'",A)
    assert writer("select count(*) from public.experiment_samples where experiment_id='"+identifier+"' and raw_text is not null",A)[0]=='0'

def test_protected_provenance_and_owner_deletion(writer):
    r=receipt();data=json.loads(r['payload']);identifier=data['id']
    writer(call(r),A)
    writer("update public.experiment_samples set provenance_label='KNOWN_UNWATERMARKED' where id='"+data['samples'][0]['id']+"'",A,succeeds=False)
    writer("delete from public.experiments where id='"+identifier+"'",A)
    assert writer("select count(*) from public.robustness_runs where experiment_id='"+identifier+"'",A)[0]=='0'

@pytest.mark.parametrize('table',['detection_results','robustness_runs'])
@pytest.mark.parametrize('operation',['update','delete'])
def test_clients_cannot_mutate_trusted_records(writer,table,operation):
    statement=f'delete from public.{table}' if operation=='delete' else f'update public.{table} set user_id=user_id'
    writer(statement,A,succeeds=False)
    writer(statement,B,succeeds=False)

def test_anonymous_cannot_execute_or_read(writer):
    writer(call(receipt()),A,role='anon',succeeds=False)
    writer('select * from public.robustness_runs',A,role='anon',succeeds=False)

def test_expired_receipt_and_review_text_rejected(writer):
    value=run();value['experiment_id']=str(uuid4())
    expired=issue(value,A,KEY,now=1)
    writer(call(expired),A,succeeds=False)
    writer(call(receipt(),",null,null,false,'{\"meaning\":\"private text\",\"omissions\":\"no\",\"facts\":\"no\"}'::jsonb"),A,succeeds=False)

def test_concurrent_identical_save_is_idempotent(writer):
    from concurrent.futures import ThreadPoolExecutor
    r=receipt();identifier=json.loads(r['payload'])['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:writer(call(r),A)[0],range(2)))
    assert results==[identifier,identifier]
    assert writer("select count(*) from public.detection_results where experiment_id='"+identifier+"'",A)[0]=='2'

def test_changed_review_on_replay_cannot_silently_replace_saved_review(writer):
    r=receipt();writer(call(r),A)
    writer(call(r,",null,null,false,'{\"meaning\":\"yes\",\"omissions\":\"no\",\"facts\":\"no\"}'::jsonb"),A,succeeds=False)

def test_retry_retention_text_and_optout_consistency(writer):
    r=receipt();identifier=json.loads(r['payload'])['id']
    writer("insert into public.profiles(id,retain_text) values('"+A+"',true) on conflict(id) do update set retain_text=true",A)
    exact=call(r,",'private original','private child',true")
    writer(exact,A);writer(exact,A)
    writer(call(r,",'changed','private child',true"),A,succeeds=False)
    writer(call(r),A,succeeds=False)
    writer("update public.profiles set retain_text=false where id='"+A+"'",A)
    assert writer(exact,A)[0]==identifier
    assert writer("select count(*) from public.experiment_samples where experiment_id='"+identifier+"' and raw_text is not null",A)[0]=='0'
    r2=receipt();writer(call(r2),A)
    writer(call(r2,",'private original','private child',true"),A,succeeds=False)

def test_writer_cannot_create_schema_objects(writer):
    for schema in ['public','auth','extensions','watermarklab_private']:
        writer('create table '+schema+'.forbidden_writer_object(id integer)',A,role='watermarklab_run_writer',succeeds=False)

def resign(doc):
    """Trusted dummy-key signing to exercise SQL validation independently."""
    import hmac,hashlib
    payload=json.dumps(doc,separators=(',',':'))
    return {'payload':payload,'key_id':'v1','signature':hmac.new(bytes.fromhex(KEY),('receipt-v1\nv1\n'+payload).encode(),hashlib.sha256).hexdigest()}

def test_deleted_experiment_cannot_be_recreated_by_receipt(writer):
    r=receipt();identifier=json.loads(r['payload'])['id']
    assert writer(call(r),A)[0]==identifier
    assert writer(call(r),A)[0]==identifier
    writer("delete from public.experiments where id='"+identifier+"'",A)
    assert writer("select count(*) from watermarklab_private.receipt_consumptions where experiment_id='"+identifier+"'")[0]=='1'
    result=writer(call(r),A,succeeds=False)
    assert 'already consumed' in result[1]
    assert writer("select count(*) from public.experiments where id='"+identifier+"'",A)[0]=='0'

@pytest.mark.parametrize('operation',['select * from','delete from','update'])
def test_ledger_cannot_be_read_or_erased_by_clients(writer,operation):
    statement=operation+' watermarklab_private.receipt_consumptions'
    if operation=='update':statement+=' set expires_at=clock_timestamp()'
    for role in ['anon','authenticated']:
        writer(statement,A,role=role,succeeds=False)

def test_expired_ledger_cleanup_never_revives_receipt(writer):
    r=receipt();doc=json.loads(r['payload']);identifier=doc['id']
    writer(call(r),A)
    writer("delete from public.experiments where id='"+identifier+"'",A)
    # Real expired signed fixture, not a forged unsigned request.
    old_id=str(uuid4())
    expired_doc={**doc,'id':old_id,'issued':1,'expires':1801};expired=resign(expired_doc)
    writer("insert into watermarklab_private.receipt_consumptions values('"+old_id+"',decode('"+'00'*32+"','hex'),to_timestamp(1801))")
    writer((ROOT/'supabase/maintenance/cleanup_expired_receipts.sql').read_text())
    assert writer("select count(*) from watermarklab_private.receipt_consumptions where experiment_id='"+old_id+"'")[0]=='0'
    assert writer("select count(*) from watermarklab_private.receipt_consumptions where experiment_id='"+identifier+"'")[0]=='1'
    writer(call(expired),A,succeeds=False)
    writer(call(r),A,succeeds=False)

@pytest.mark.parametrize('field,value',[
    ('z_score',None),('z_score','NaN'),('z_score','Infinity'),('z_score','-Infinity'),
    ('threshold',None),('threshold',5),('threshold','NaN'),
    ('character_count',None),('character_count',0),('character_count',20001),
    ('token_count',None),('token_count',-1),('token_count',1.5),('token_count',True),('token_count',2147483648),
    ('scored_token_count',None),('scored_token_count',49),('scored_token_count',102),
    ('green_token_count',101),('execution_ms',-1),('execution_ms','Infinity'),
    ('execution_ms',None),('repeated_pair_count',-1),('g_value_trials',-1),('z_score',4),
])
def test_invalid_native_numbers_rollback_consumption(writer,field,value):
    doc=json.loads(receipt()['payload']);doc['samples'][0]['evidence'][field]=value
    writer(call(resign(doc)),A,succeeds=False)
    assert writer("select count(*) from watermarklab_private.receipt_consumptions where experiment_id='"+doc['id']+"'")[0]=='0'
    assert writer("select count(*) from public.experiments where id='"+doc['id']+"'",A)[0]=='0'

@pytest.mark.parametrize('value',[-0.01,1.01,'NaN','Infinity','-Infinity',None])
def test_synthid_invalid_p_value(writer,value):
    doc=json.loads(receipt()['payload'])
    for sample in doc['samples']:
        sample['evidence'].update(method='SYNTHID',profile_id='synthid-threefry-gpt2-cpu-v1',z_score=None,p_value=value,threshold=0.01)
    writer(call(resign(doc)),A,succeeds=False)

def test_missing_numeric_field_rejected(writer):
    doc=json.loads(receipt()['payload']);del doc['samples'][0]['evidence']['token_count']
    writer(call(resign(doc)),A,succeeds=False)

def test_transaction_start_time_cannot_extend_receipt_expiry(writer):
    import time
    doc=json.loads(receipt()['payload']);doc['expires']=int(time.time())+1;doc['issued']=doc['expires']-1800
    _,error=writer('select pg_sleep(2); '+call(resign(doc)),A,succeeds=False)
    assert 'lifetime' in error or 'expired' in error

@pytest.mark.parametrize('p,verdict',[(0,'DETECTED'),(1,'NOT DETECTED')])
def test_native_p_value_endpoints_are_valid(writer,p,verdict):
    doc=json.loads(receipt()['payload'])
    for sample in doc['samples']:
        sample['evidence'].update(method='SYNTHID',profile_id='synthid-threefry-gpt2-cpu-v1',z_score=None,p_value=p,threshold=0.01,verdict=verdict)
    assert writer(call(resign(doc)),A)[0]==doc['id']

def test_writer_cannot_remove_or_change_consumption(writer):
    writer('delete from watermarklab_private.receipt_consumptions',A,role='watermarklab_run_writer',succeeds=False)
    writer('update watermarklab_private.receipt_consumptions set expires_at=clock_timestamp()',A,role='watermarklab_run_writer',succeeds=False)

def test_receipt_expiring_while_waiting_for_run_lock_is_rejected(writer):
    from concurrent.futures import ThreadPoolExecutor
    import time
    doc=json.loads(receipt()['payload']);identifier=doc['id']
    with ThreadPoolExecutor(max_workers=1) as pool:
        held=pool.submit(writer,"select pg_advisory_xact_lock(hashtextextended('"+identifier+"',0)); select pg_sleep(6)",A)
        deadline=time.monotonic()+2
        while writer("select count(*) from pg_locks where locktype='advisory' and granted")[0]=='0':
            assert time.monotonic()<deadline
            time.sleep(0.02)
        doc['expires']=int(time.time())+3;doc['issued']=doc['expires']-1800
        _,error=writer(call(resign(doc)),A,succeeds=False)
        held.result()
    assert 'Receipt expired' in error
    assert writer("select count(*) from watermarklab_private.receipt_consumptions where experiment_id='"+identifier+"'")[0]=='0'

@pytest.mark.parametrize('method',['KGW','SYNTHID'])
def test_actual_cpu_pair_receipt_saves_locally(writer,method):
    from fastapi.testclient import TestClient
    from app.core.config import Settings,BACKEND_ROOT
    from app.core.security import Identity,require_user
    from app.main import create_app
    app=create_app(Settings(_env_file=None,robustness_signing_key=KEY))
    app.dependency_overrides[require_user]=lambda:Identity(A,'dummy-token')
    samples=json.loads((BACKEND_ROOT/f'research/{method.lower()}_pilot.json').read_text())['samples']
    source=next(s['text'] for s in samples if s['provenance']=='KNOWN_WATERMARKED' and (method=='KGW' or s.get('implementation')=='deepmind-threefry'))
    profile='kgw-gpt2-cpu-v1' if method=='KGW' else 'synthid-threefry-gpt2-cpu-v1'
    with TestClient(app) as client:
        response=client.post('/api/v1/compare',json={'text':source,'method':method,'profile_id':profile,'compatibility_confirmed':True,'operation':'shorten','strength':25})
        assert response.status_code==200
        result=response.json()
    assert result['original']['detection']['verdict']=='DETECTED'
    assert writer(call(result['receipt']),A)[0]==result['experiment_id']
