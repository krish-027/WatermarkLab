import json
from types import SimpleNamespace
import httpx
import pytest
from scripts.hosted_diagnostics import response_diagnostic,sanitize
from scripts.run_hosted_tests import SafeResults

def test_response_sanitization_excludes_all_raw_material():
    response=httpx.Response(400,headers={'X-WatermarkLab-Database-Diagnostic':json.dumps({'upstream_http_status':400,'database_stage':'save_rpc','postgrest_code':'23514','sqlstate':'23514','rpc_function':'save_robustness_run'})},json={'code':'23514','message':'private-marker','details':'private-marker','hint':'private-marker','payload':'private-marker'})
    result=response_diagnostic(response,'save_endpoint')
    assert result['sqlstate']=='23514' and result['postgrest_code']=='23514'
    assert 'private-marker' not in json.dumps(result)
    assert result['rpc_function']=='save_robustness_run'

def test_unknown_fields_codes_and_messages_do_not_escape():
    result=response_diagnostic(httpx.Response(503,json={'code':'SECRET','detail':'private-marker'}),'private-marker')
    assert result['postgrest_code'] is None and result['request_stage'] is None
    assert 'private-marker' not in json.dumps(result)
    assert sanitize({'http_status':True,'signature':'secret','request_stage':[],'application_code':{}})['http_status'] is None

def test_masked_database_error_cannot_recover_upstream_code():
    result=response_diagnostic(httpx.Response(503,json={'detail':'Database request failed. Check migration and grants.'}),'save_endpoint')
    assert result['application_code']=='database_request_failed'
    assert result['sqlstate'] is None and result['postgrest_code'] is None

def test_safe_runner_sanitizes_structured_properties():
    plugin=SafeResults()
    plugin.pytest_runtest_logreport(SimpleNamespace(when='call',failed=True,skipped=False,nodeid='test',outcome='failed',longrepr='private-marker',user_properties=[('safe_http_diagnostic',{'http_status':503,'request_stage':'save_rpc','payload':'private-marker'})]))
    assert 'private-marker' not in json.dumps(plugin.results)
    assert plugin.results[0]['http_diagnostics'][0]['http_status']==503


@pytest.mark.parametrize('code,expected', [('42501','42501'), ('PGRST202','PGRST202'), ('SECRET123',None), ('99999',None)])
def test_safe_runner_denial_code_allowlist(code, expected):
    plugin=SafeResults()
    plugin.pytest_runtest_logreport(SimpleNamespace(when='call',failed=True,skipped=False,
        nodeid='test',outcome='failed',longrepr=f'DENIAL_STATUS=403;CODE={code} private-marker',user_properties=[]))
    assert plugin.results[0]['database_code'] == expected
    assert plugin.results[0]['denial_status'] == '403'
    assert 'private-marker' not in json.dumps(plugin.results)
    if expected is None: assert code not in json.dumps(plugin.results)
