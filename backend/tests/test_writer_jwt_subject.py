"""Local PostgreSQL claim extraction and unchanged security boundaries."""
import json
import pytest
from test_migration_local import sql, ROOT, A, B
from test_receipt_sql import writer, receipt, call

MIGRATION = ROOT/'supabase/migrations/202611040002_writer_jwt_subject.sql'


def test_body_diff_is_limited_to_subject_extraction():
    old = (ROOT/'supabase/migrations/202610310001_robustness_receipts.sql').read_text()
    old = old[old.index('create function public.save_robustness_run('):]
    old = old[:old.index('end $$;')+len('end $$;')]
    new = MIGRATION.read_text()
    new = new[new.index('create or replace function'):new.index('\ncommit;')]
    assert 'auth.uid()' not in new
    new = new.replace('create or replace function','create function',1)
    new = new.replace(' request_user_id uuid;\n','',1)
    start = new.index(' begin\n  request_user_id :=')
    end = new.index('\n if request_user_id is null',start)
    new = new[:start]+new[end+1:]
    new = new.replace('request_user_id','auth.uid()')
    assert new == old


@pytest.mark.parametrize('legacy,claims', [(A,''),('',json.dumps({'sub':A})),('',json.dumps({'sub':A,'role':'authenticated'})),(A,json.dumps({'sub':B})),(A,'malformed')])
def test_claim_sources_and_precedence_without_auth_usage(writer,legacy,claims):
    r=receipt(); identifier=json.loads(r['payload'])['id']
    statement=f"set local \"request.jwt.claims\"='{claims}'; "+call(r)
    assert writer(statement,legacy)[0]==identifier
    assert writer("select has_schema_privilege('watermarklab_run_writer','auth','USAGE')")[0]=='f'


@pytest.mark.parametrize('legacy,claims', [('', ''),('', '{}'),('', '{"sub":null}'),('bad-uuid',''),('', '{"sub":"bad-uuid"}'),('', 'malformed'),('', '{"sub":""}')])
def test_missing_or_invalid_claims_rejected_safely(writer,legacy,claims):
    r=receipt()
    _,error=writer(f"set local \"request.jwt.claims\"='{claims}'; "+call(r),legacy,succeeds=False)
    assert 'Authentication required' in error or 'Invalid authentication claims' in error
    assert 'bad-uuid' not in error and 'malformed' not in error
    identifier=json.loads(r['payload'])['id']
    assert writer(f"select count(*) from public.experiments where id='{identifier}'")[0]=='0'


def test_fallback_subject_must_match_signed_owner(writer):
    _,error=writer(f"set local \"request.jwt.claims\"='{{\"sub\":\"{B}\"}}'; "+call(receipt()),'',succeeds=False)
    assert 'Invalid owner or receipt lifetime' in error


def test_security_and_schema_restrictions(writer):
    assert writer("select r.rolname,p.prosecdef,p.proconfig::text from pg_proc p join pg_roles r on r.oid=p.proowner where p.oid='public.save_robustness_run(text,text,text,text,text,boolean,jsonb)'::regprocedure")[0]=='watermarklab_run_writer|t|{"search_path=\\"\\""}'
    assert writer("select rolcanlogin,rolinherit,rolbypassrls from pg_roles where rolname='watermarklab_run_writer'")[0]=='f|f|f'
    assert writer("select has_schema_privilege('watermarklab_run_writer','auth','USAGE'),pg_has_role('postgres','watermarklab_run_writer','SET')")[0]=='f|f'


def test_nonowner_cannot_apply_replacement_without_owner_authority(writer):
    # Local postgres is deliberately not a superuser and has no writer membership.
    _,error=writer(MIGRATION.read_text(),login='postgres',succeeds=False)
    assert 'permission denied' in error or 'must be owner' in error
