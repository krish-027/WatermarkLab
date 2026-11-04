"""Opt-in SQL contract tests on an isolated local PostgreSQL cluster.

Minimal auth schema/UID stand-in tests PostgreSQL behavior, NOT Supabase Auth.
No hosted project, local env credentials or existing database is accessed.
"""
import os
from pathlib import Path
import socket
import subprocess
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = Path(r'C:\Program Files\PostgreSQL\18\bin')
A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'


@pytest.fixture(scope='module')
def sql():
    if os.getenv('WATERMARKLAB_LOCAL_SQL') != '1':
        pytest.skip('Opt-in isolated local PostgreSQL tests')
    cluster = ROOT / '.cache' / ('pg-review-' + uuid4().hex)
    cluster.parent.mkdir(exist_ok=True)
    assert cluster.resolve().is_relative_to((ROOT / '.cache').resolve())
    def command(name, *args):
        if name == 'pg_ctl':
            return subprocess.run([str(BIN / 'pg_ctl.exe'), *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
        return subprocess.run([str(BIN / (name + '.exe')), *args], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
    result = command('initdb', '-D', str(cluster), '-U', 'wl_test_admin', '--auth=trust', '--encoding=UTF8', '--no-locale')
    assert result.returncode == 0, result.stderr
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = str(sock.getsockname()[1])
    result = command('pg_ctl','-D',str(cluster),'-l',str(cluster.parent / (cluster.name + '.log')),'-o',f'-h 127.0.0.1 -p {port}','-w','start')
    assert result.returncode == 0, result.stderr
    def run(statement, user=None, role='authenticated', succeeds=True, login='wl_test_admin'):
        if user is not None:
            statement = f"begin; set local role {role}; set local \"request.jwt.claim.sub\"='{user}'; {statement}; commit;"
        result = command('psql','-X','-q','-t','-A','-h','127.0.0.1','-p',port,'-U',login,'-d','postgres','-v','ON_ERROR_STOP=1','-c',statement)
        if succeeds:
            assert result.returncode == 0, result.stderr
        else:
            assert result.returncode != 0, 'Expected database rejection'
        return result.stdout.strip(), result.stderr
    try:
        run(f"create role postgres login nosuperuser; create role anon; create role authenticated; create schema auth; create table auth.users(id uuid primary key); insert into auth.users values ('{A}'),('{B}'); create function auth.uid() returns uuid language sql stable as $$ select coalesce(nullif(current_setting('request.jwt.claim.sub',true),''),nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid $$; grant usage on schema auth to anon,authenticated;")
        run((ROOT / 'supabase/migrations/202610300001_ownership.sql').read_text(encoding='utf-8'))
        run((ROOT / 'supabase/tests/grants_and_policies.sql').read_text(encoding='utf-8'))
        yield run
    finally:
        result = command('pg_ctl','-D',str(cluster),'-m','fast','-w','stop')
        assert result.returncode == 0, 'Could not stop owned local test cluster'
        # Retain ignored files for inspection; never delete an existing/system cluster.


@pytest.fixture
def rows(sql):
    experiment, sample, result = [str(uuid4()) for _ in range(3)]
    sql(f"insert into public.experiments(id,user_id,title) values('{experiment}','{A}','local SQL fixture'); insert into public.experiment_samples(id,user_id,experiment_id) values('{sample}','{A}','{experiment}'); insert into public.detection_results(id,user_id,experiment_id,sample_id,detector_method,verdict) values('{result}','{A}','{experiment}','{sample}','KGW','UNAVAILABLE')")
    yield experiment,sample,result
    sql(f"delete from public.experiments where id='{experiment}'")


@pytest.mark.parametrize('table', ['profiles','experiments','experiment_samples','detection_results'])
def test_sql_select_ownership_and_anon_grants(sql, rows, table):
    experiment,sample,result = rows
    if table=='profiles': sql(f"insert into public.profiles(id) values('{A}') on conflict do nothing")
    row_id={'profiles':A,'experiments':experiment,'experiment_samples':sample,'detection_results':result}[table]
    query=f"select count(*) from public.{table} where id='{row_id}'"
    assert sql(query,A)[0]=='1'
    assert sql(query,B)[0]=='0'
    sql(query,B,role='anon',succeeds=False)


@pytest.mark.parametrize('operation', ['insert','update','delete'])
def test_sql_detector_evidence_is_read_only(sql,rows,operation):
    experiment,sample,result=rows
    statements={
        'insert':f"insert into public.detection_results(user_id,experiment_id,sample_id,detector_method,verdict) values('{A}','{experiment}','{sample}','KGW','UNAVAILABLE')",
        'update':f"update public.detection_results set verdict='DETECTED' where id='{result}'",
        'delete':f"delete from public.detection_results where id='{result}'",
    }
    for user in [A,B]: sql(statements[operation],user,succeeds=False)


def test_sql_insert_cannot_spoof_owner_or_parent(sql,rows):
    experiment,sample,_=rows
    sql(f"insert into public.experiments(user_id,title) values('{A}','spoof')",B,succeeds=False)
    sql(f"insert into public.experiment_samples(user_id,experiment_id) values('{B}','{experiment}')",B,succeeds=False)
    other=str(uuid4())
    sql(f"insert into public.experiments(id,user_id,title) values('{other}','{B}','own')",B)
    sql(f"insert into public.experiment_samples(user_id,experiment_id,parent_sample_id) values('{B}','{other}','{sample}')",B,succeeds=False)
    sql(f"delete from public.experiments where id='{other}'",B)


def test_sql_update_cannot_transfer_owner(sql,rows):
    experiment,sample,_=rows
    for table,row_id in [('experiments',experiment),('experiment_samples',sample)]:
        sql(f"update public.{table} set user_id='{B}' where id='{row_id}'",A,succeeds=False)
        assert sql(f"update public.{table} set user_id='{B}' where id='{row_id}' returning id",B)[0]==''


def test_sql_delete_filters_other_user_and_allows_owner_cascade(sql,rows):
    experiment,sample,_=rows
    assert sql(f"delete from public.experiment_samples where id='{sample}' returning id",B)[0]==''
    assert sql(f"delete from public.experiments where id='{experiment}' returning id",B)[0]==''
    assert sql(f"delete from public.experiments where id='{experiment}' returning id",A)[0]==experiment
    assert sql(f"select count(*) from public.detection_results where experiment_id='{experiment}'",A)[0]=='0'


def test_sql_both_retention_gates_and_opt_out_purge(sql,rows):
    _,sample,_=rows
    sql(f"insert into public.profiles(id,retain_text) values('{A}',false) on conflict(id) do update set retain_text=false")
    sql(f"update public.experiment_samples set raw_text='fixture',retention_consent=true where id='{sample}'",A,succeeds=False)
    sql(f"update public.profiles set retain_text=true where id='{A}'",A)
    sql(f"update public.experiment_samples set raw_text='fixture',retention_consent=false where id='{sample}'",A,succeeds=False)
    sql(f"update public.experiment_samples set raw_text='fixture',retention_consent=true where id='{sample}'",A)
    sql(f"update public.profiles set retain_text=false where id='{A}'",A)
    assert sql(f"select raw_text is null and not retention_consent from public.experiment_samples where id='{sample}'",A)[0]=='t'
    sql(f"update public.profiles set retain_text=true where id='{A}'",A)
    sql(f"update public.experiment_samples set raw_text='fixture',retention_consent=true where id='{sample}'",A)
    sql(f"delete from public.profiles where id='{A}'",A)
    assert sql(f"select raw_text is null from public.experiment_samples where id='{sample}'",A)[0]=='t'
    sql(f"update public.experiment_samples set raw_text='fixture',retention_consent=true where id='{sample}'",A,succeeds=False)


def test_sql_parent_delete_is_blocked_but_experiment_delete_succeeds(sql,rows):
    experiment,parent,_=rows
    child=str(uuid4())
    sql(f"insert into public.experiment_samples(id,user_id,experiment_id,parent_sample_id) values('{child}','{A}','{experiment}','{parent}')",A)
    sql(f"delete from public.experiment_samples where id='{parent}'",A,succeeds=False)
    sql(f"update public.experiment_samples set parent_sample_id='{child}' where id='{parent}'",A,succeeds=False)
    sql(f"delete from public.experiments where id='{experiment}'",A)


@pytest.mark.parametrize('table', ['profiles','experiments','experiment_samples'])
def test_sql_mutable_insert_policy(sql,rows,table):
    experiment,_,_=rows
    row_id=str(uuid4())
    if table=='profiles':
        sql(f"delete from public.profiles where id='{A}'")
        row_id=A
        insert=f"insert into public.profiles(id) values('{A}')"
    elif table=='experiments':
        insert=f"insert into public.experiments(id,user_id,title) values('{row_id}','{A}','insert test')"
    else:
        insert=f"insert into public.experiment_samples(id,user_id,experiment_id) values('{row_id}','{A}','{experiment}')"
    error=sql(insert,B,succeeds=False)[1]
    assert 'row-level security' in error
    sql(insert,A)
    assert sql(f"select count(*) from public.{table} where id='{row_id}'",A)[0]=='1'
    sql(f"delete from public.{table} where id='{row_id}'",A)


@pytest.mark.parametrize('table', ['profiles','experiments','experiment_samples'])
def test_sql_mutable_update_policy(sql,rows,table):
    experiment,sample,_=rows
    if table=='profiles': sql(f"insert into public.profiles(id) values('{A}') on conflict do nothing")
    row_id={'profiles':A,'experiments':experiment,'experiment_samples':sample}[table]
    field,value={'profiles':('display_name','updated'),'experiments':('title','updated'),'experiment_samples':('provenance_label','UNKNOWN')}[table]
    query=f"update public.{table} set {field}='{value}' where id='{row_id}' returning id"
    assert sql(query,B)[0]==''
    assert sql(query,A)[0]==row_id
    owner='id' if table=='profiles' else 'user_id'
    sql(f"update public.{table} set {owner}='{B}' where id='{row_id}'",A,succeeds=False)


@pytest.mark.parametrize('table', ['profiles','experiments','experiment_samples'])
def test_sql_mutable_delete_policy(sql,rows,table):
    experiment,sample,_=rows
    if table=='profiles': sql(f"insert into public.profiles(id) values('{A}') on conflict do nothing")
    row_id={'profiles':A,'experiments':experiment,'experiment_samples':sample}[table]
    query=f"delete from public.{table} where id='{row_id}' returning id"
    assert sql(query,B)[0]==''
    assert sql(f"select count(*) from public.{table} where id='{row_id}'",A)[0]=='1'
    assert sql(query,A)[0]==row_id
