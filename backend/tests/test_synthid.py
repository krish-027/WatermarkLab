"""Real pinned DeepMind core and genuine Phase 5A fixtures.

Local API contracts override identity only; hosted-auth browser checks are separate.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import math

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.core.config import BACKEND_ROOT, Settings
from app.core.security import Identity, require_user
from app.main import create_app
from app.schemas.analysis import AnalysisInput, AnalysisResult
from app.watermark.synthid_adapter import SynthIDAdapter, PROFILE_ID, ALPHA

PILOT=json.loads((BACKEND_ROOT/'research/synthid_pilot.json').read_text(encoding='utf-8'))
ROWS=[r for r in PILOT['samples'] if r['implementation']=='deepmind-threefry']

def payload(text,**kwargs):
    return AnalysisInput(text=text,method='SYNTHID',profile_id=PROFILE_ID,compatibility_confirmed=True,**kwargs)

@pytest.fixture(scope='module')
def adapter():
    adapter=SynthIDAdapter()
    assert adapter.capabilities()['status']=='ready'  # Missing integration fails, never silently skips.
    return adapter

@pytest.mark.parametrize('row',ROWS,ids=lambda r:r['prompt_id']+'-'+r['provenance'])
def test_genuine_native_p_value_counts_tokenizer_and_verdict(adapter,row):
    result=adapter.analyze(payload(row['text'],provenance=row['provenance']))
    assert result.p_value==row['text_evidence']['native_p_value']
    assert result.native=={'p_value':result.p_value}
    assert result.scored_token_count==row['text_evidence']['scored_positions']
    assert result.g_value_ones==row['text_evidence']['ones']
    assert result.g_value_trials==row['text_evidence']['trials']
    assert result.token_count==len(row['generated_token_ids'])==200
    assert adapter._tokenizer(row['text'],add_special_tokens=False)['input_ids']==row['generated_token_ids']
    assert result.verdict==('DETECTED' if row['provenance']=='KNOWN_WATERMARKED' else 'NOT DETECTED')
    assert result.z_score is None and result.raw_score is None and result.green_token_count is None
    assert result.provenance==row['provenance'] and result.compatibility_status=='declared'

def test_exact_binomial_tail_independent_integer_calculation(adapter):
    # Ten distinct 5-grams => 300 binary trials. Integer arithmetic independently
    # evaluates the same null tail, not an approximate normal/z conversion.
    import torch
    ids=torch.arange(14).reshape(1,-1)
    g,mask=adapter._processor.compute_g_values_and_mask(ids,eos_token_id=50256)
    n=int(mask.sum())*30
    ones=int((g*mask.unsqueeze(-1)).sum())
    expected=sum(math.comb(n,k) for k in range(ones,n+1))/2**n
    actual=float(adapter._detector.p_value(ids)[0])
    assert actual==pytest.approx(expected,rel=1e-13)

@pytest.mark.parametrize('profile,confirmed,status',[(None,False,'unknown'),('hf-sampling-table',True,'unsupported'),('kgw-gpt2-cpu-v1',True,'unsupported'),('gemini-production',True,'unsupported'),(PROFILE_ID,False,'unknown')])
def test_unknown_or_incompatible_profiles_never_score(adapter,profile,confirmed,status):
    result=adapter.analyze(AnalysisInput(text=ROWS[0]['text'],method='SYNTHID',profile_id=profile,compatibility_confirmed=confirmed))
    assert result.verdict=='INCONCLUSIVE' and result.compatibility_status==status
    assert result.native is None and result.token_count is None and result.p_value is None

@pytest.mark.parametrize('text',['hello','A short research sentence.','🌍 café 中文 e\u0301','  word\n'])
def test_short_unicode_no_normalization(adapter,text):
    result=adapter.analyze(payload(text))
    assert result.verdict=='INCONCLUSIVE'
    assert result.token_count==len(adapter._tokenizer(text,add_special_tokens=False)['input_ids'])
    assert result.p_value is not None
    assert payload(text).text==text

def test_no_scored_positions_native_one_still_inconclusive(adapter):
    result=adapter.analyze(payload('hello'))
    assert result.scored_token_count==0 and result.p_value==1
    assert result.verdict=='INCONCLUSIVE' and result.g_value_trials==0

def test_repetition_masks_reduce_effective_length(adapter):
    result=adapter.analyze(payload('one two three four five six ' * 30))
    assert result.repeated_context_count>0 and result.masked_position_count>0
    assert result.scored_token_count<50 and result.verdict=='INCONCLUSIVE'

def test_eos_and_combined_masks_on_actual_tokenized_input(adapter):
    result=adapter.analyze(payload('one two three four five six <|endoftext|> '+ROWS[0]['text']))
    assert result.eos_masked_position_count>100
    assert result.scored_token_count<50 and result.verdict=='INCONCLUSIVE'
    assert result.masked_position_count==max(0,result.token_count-4)-result.scored_token_count

def test_full_profile_history_limit_no_truncation(adapter):
    result=adapter.analyze(payload('word ' * 1100))
    assert result.token_count>1024 and result.p_value is None and result.verdict=='INCONCLUSIVE'
    assert '1024-token' in result.warnings[0]
    result=adapter.analyze(payload(ROWS[0]['text']),max_tokens=50)
    assert result.token_count==200 and result.p_value is None

def test_missing_and_tampered_setup(tmp_path):
    assert SynthIDAdapter(assets=tmp_path).capabilities()['status']=='setup required'
    assert SynthIDAdapter(reference=tmp_path).analyze(payload('text')).verdict=='UNAVAILABLE'
    (tmp_path/'config.json').write_text('{}')
    assert SynthIDAdapter(assets=tmp_path).analyze(payload('text')).native is None

def test_dependency_mismatch_is_unavailable(monkeypatch):
    monkeypatch.setattr('app.watermark.synthid_adapter.importlib.metadata.version',lambda _: 'unverified')
    assert SynthIDAdapter().capabilities()['status']=='setup required'

def test_strict_separation_of_response_types():
    for method,extra in [('SYNTHID',{'z_score':4}),('KGW',{'p_value':.01})]:
        with pytest.raises(ValidationError):
            AnalysisResult(method=method,profile_id=None,verdict='INCONCLUSIVE',provenance='UNKNOWN',character_count=0,**extra)

def test_decision_boundary_is_inclusive_without_changing_native_math(adapter,monkeypatch):
    original=float(adapter._detector.p_value(__import__('torch').tensor([ROWS[0]['generated_token_ids']]))[0])
    # Boundary-only policy test: native math/parity tested above. P-value transport
    # is explicitly stubbed here solely to exercise equality, not scientific acceptance.
    monkeypatch.setattr(adapter._detector,'p_value',lambda _: [ALPHA])
    assert adapter.analyze(payload(ROWS[0]['text'])).verdict=='DETECTED'
    monkeypatch.setattr(adapter._detector,'p_value',lambda _: [math.nextafter(ALPHA,math.inf)])
    assert adapter.analyze(payload(ROWS[0]['text'])).verdict=='NOT DETECTED'
    assert original==ROWS[0]['text_evidence']['native_p_value']

def test_concurrent_calls_have_no_state_leakage(adapter):
    def run(_):
        try: return adapter.analyze(payload(ROWS[0]['text']))
        except BlockingIOError: return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(run,range(8)))
    assert any(r for r in results)
    assert all(r is None or r.p_value==ROWS[0]['text_evidence']['native_p_value'] for r in results)

def test_provenance_is_independent_of_evidence(adapter):
    result=adapter.analyze(payload(ROWS[0]['text'],provenance='UNKNOWN'))
    assert result.provenance=='UNKNOWN' and result.verdict=='DETECTED'

def test_concurrent_kgw_and_synthid_keep_method_specific_evidence(adapter):
    from app.watermark.kgw_adapter import KGWAdapter, PROFILE_ID as KGW_PROFILE
    kgw=KGWAdapter()
    assert kgw.capabilities()['status']=='ready'
    sample=json.loads((BACKEND_ROOT/'research/kgw_pilot.json').read_text(encoding='utf-8'))['samples'][0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        synthid_future=pool.submit(adapter.analyze,payload(ROWS[0]['text']))
        kgw_future=pool.submit(kgw.analyze,AnalysisInput(text=sample['text'],profile_id=KGW_PROFILE,compatibility_confirmed=True))
        synthid_result,kgw_result=synthid_future.result(),kgw_future.result()
    assert synthid_result.p_value==ROWS[0]['text_evidence']['native_p_value'] and synthid_result.z_score is None
    assert kgw_result.native==sample['native'] and kgw_result.p_value is None

@pytest.fixture
def api(adapter):
    app=create_app(Settings(_env_file=None))
    app.state.synthid=adapter
    app.dependency_overrides[require_user]=lambda: Identity('local-contract-only','unit-not-hosted')
    with TestClient(app) as client: yield client

def test_api_native_evidence_no_text_keys_or_kgw_scores(api):
    result=api.post('/api/v1/analyze',json=payload(ROWS[0]['text']).model_dump())
    assert result.status_code==200
    assert result.json()['p_value']==ROWS[0]['text_evidence']['native_p_value']
    assert result.json()['z_score'] is None and result.json()['raw_score'] is None
    assert ROWS[0]['text'] not in result.text and 'key' not in result.json()

def test_capabilities_and_samples_public_config_no_keys(api):
    cap=api.get('/api/v1/capabilities').json()['detectors'][1]
    assert cap['status']=='ready' and cap['max_tokens']==1024
    assert not {'key','base_key','keys'} & cap.keys()
    rows=api.get('/api/v1/synthid/samples').json()
    assert len(rows)==4 and {r['profile_id'] for r in rows}=={PROFILE_ID}
    assert [r['id'] for r in rows]==['synthid-pilot-1-wm','synthid-pilot-1-control','synthid-pilot-2-wm','synthid-pilot-2-control']
    assert all(not {'native','text_evidence','configurations','key'} & r.keys() for r in rows)

def test_synthid_auth_and_forged_bearer_are_rejected():
    app=create_app(Settings(_env_file=None,supabase_url='https://example.supabase.co',supabase_publishable_key='sb_publishable_unit'))
    with TestClient(app) as client:
        assert client.post('/api/v1/analyze',json=payload('text').model_dump()).status_code==401
        assert client.get('/api/v1/synthid/samples').status_code==401
        assert client.post('/api/v1/analyze',json=payload('text').model_dump(),headers={'Authorization':'Bearer forged'}).status_code==401

def test_busy_returns_retryable_response(api,adapter):
    adapter._lock.acquire()
    try:
        response=api.post('/api/v1/analyze',json=payload('text').model_dump())
        assert response.status_code==429 and response.headers['Retry-After']=='2'
    finally: adapter._lock.release()

def test_validation_and_request_limits_do_not_echo_input(api):
    for body in [{'text':'secret-marker','method':'SYNTHID','p_value':0}, {'text':'x'*20001,'method':'SYNTHID'}]:
        response=api.post('/api/v1/analyze',json=body)
        assert response.status_code==422 and 'secret-marker' not in response.text
    assert api.post('/api/v1/analyze',content=b'x'*131073).status_code==413
