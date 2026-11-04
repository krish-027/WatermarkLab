"""Real pinned reference and genuine generated fixtures; no fake detector scores.

HTTP contract tests below override identity only, explicitly not hosted-auth tests.
"""
import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.core.config import BACKEND_ROOT, Settings
from app.core.security import Identity, require_user
from app.main import create_app
from app.schemas.analysis import AnalysisInput
from app.watermark.kgw_adapter import KGWAdapter, PROFILE_ID, REFERENCE

PILOT = json.loads((BACKEND_ROOT / 'research/kgw_pilot.json').read_text(encoding='utf-8'))

@pytest.fixture(scope='module')
def adapter():
    instance = KGWAdapter()
    # This suite fails if KGW is unavailable; never silently skip scientific acceptance.
    assert instance.capabilities()['status'] == 'ready'
    return instance

def payload(text, **kwargs):
    return AnalysisInput(text=text, profile_id=PROFILE_ID, compatibility_confirmed=True, **kwargs)

@pytest.mark.parametrize('sample', PILOT['samples'], ids=lambda s: s['id'])
def test_real_pilot_parity_and_manual_z_formula(adapter, sample):
    result = adapter.analyze(payload(sample['text'], provenance=sample['provenance']))
    assert result.native == sample['native']
    assert result.token_count == sample['retokenized_token_count']
    assert result.scored_token_count == result.token_count - 1
    expected_z = (result.green_token_count - .5 * result.scored_token_count) / math.sqrt(result.scored_token_count * .25)
    assert result.z_score == pytest.approx(expected_z, abs=1e-12)
    assert result.raw_score == result.z_score
    assert result.p_value is None
    assert result.verdict == ('DETECTED' if sample['native']['is_watermarked'] else 'NOT DETECTED')
    assert result.provenance == sample['provenance']

def test_native_strict_threshold_boundary(adapter):
    # Exercise upstream's actual detector with the decision threshold equal to its score.
    # Restore state before any further tests; production profile is immutable.
    ref = adapter._detector
    text = PILOT['samples'][0]['text']
    old = ref.config.z_threshold
    try:
        z = ref.detect_watermark(text)['score']
        ref.config.z_threshold = z
        assert ref.detect_watermark(text)['is_watermarked'] is False
        ref.config.z_threshold = math.nextafter(z, -math.inf)
        assert ref.detect_watermark(text)['is_watermarked'] is True
    finally:
        ref.config.z_threshold = old

def test_actual_greenlist_logits_bias_and_prefix(adapter):
    import torch
    ref = adapter._detector
    prefix = torch.tensor([[123, 456]])
    green = ref.utils.get_greenlist_ids(prefix[0])
    scores = torch.zeros((1, 50257))
    biased = ref.logits_processor(prefix, scores)
    assert torch.all(biased[0, green] == 2.0)
    assert int((biased == 2).sum()) == int(.5 * 50257)
    assert int((biased == 0).sum()) == 50257 - len(green)
    empty = torch.empty((1, 0), dtype=torch.long)
    assert torch.all(ref.logits_processor(empty, torch.zeros((1,50257))) == 0)

@pytest.mark.parametrize('profile,confirmed', [(None,False), ('unknown',True), (PROFILE_ID,False)])
def test_unknown_compatibility_never_scores(adapter, profile, confirmed):
    result = adapter.analyze(AnalysisInput(text=PILOT['samples'][0]['text'],profile_id=profile,compatibility_confirmed=confirmed))
    assert result.verdict == 'INCONCLUSIVE'
    assert result.native is None and result.token_count is None

@pytest.mark.parametrize('text', ['hello', 'A short sentence.', '🌍 café 中文 e\u0301'])
def test_short_and_unicode_text_is_inconclusive(adapter, text):
    result = adapter.analyze(payload(text))
    assert result.verdict == 'INCONCLUSIVE'
    assert result.token_count == len(adapter._tokenizer(text, add_special_tokens=False)['input_ids'])

def test_repetitive_input_withholds_decision_preserves_native(adapter):
    result = adapter.analyze(payload('The same phrase repeats. ' * 80))
    assert result.verdict == 'INCONCLUSIVE'
    assert result.native is not None and result.repeated_pair_count > result.scored_token_count / 2

def test_token_limit_does_not_truncate_or_score(adapter):
    result = adapter.analyze(payload(PILOT['samples'][0]['text']), max_tokens=50)
    assert result.verdict == 'INCONCLUSIVE' and result.token_count == 200
    assert result.native is None

def test_missing_assets_and_tampered_asset_are_unavailable(tmp_path):
    instance = KGWAdapter(tmp_path)
    assert instance.capabilities()['status'] == 'setup required'
    assert instance.analyze(payload('An ordinary sentence.')).verdict == 'UNAVAILABLE'
    (tmp_path / 'config.json').write_text('{}')
    assert instance.capabilities()['status'] == 'setup required'

def test_synthid_honest_unavailable(adapter):
    result = adapter.analyze(AnalysisInput(text='A sentence.',method='SYNTHID'))
    assert result.verdict == 'UNAVAILABLE' and result.native is None

def test_provenance_does_not_determine_verdict(adapter):
    result = adapter.analyze(payload(PILOT['samples'][0]['text'],provenance='UNKNOWN'))
    assert result.verdict == 'DETECTED' and result.provenance == 'UNKNOWN'

def test_concurrency_has_no_rng_races(adapter):
    def run():
        try:
            return adapter.analyze(payload(PILOT['samples'][0]['text']))
        except BlockingIOError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: run(), range(8)))
    assert any(r is not None for r in results)
    for r in results:
        if r:
            assert r.native == PILOT['samples'][0]['native']

def test_reference_source_bytes_unchanged():
    for name,digest in json.loads((REFERENCE/'SHA256SUMS.json').read_text()).items():
        assert hashlib.sha256((REFERENCE/name).read_bytes()).hexdigest() == digest

@pytest.fixture
def api(adapter):
    app = create_app(Settings(_env_file=None))
    app.state.kgw = adapter
    app.dependency_overrides[require_user] = lambda: Identity('local-contract-test', 'not-a-hosted-token')
    with TestClient(app) as client:
        yield client

def test_api_returns_actual_evidence_without_text_or_key(api):
    sample = PILOT['samples'][0]
    response = api.post('/api/v1/analyze', json=payload(sample['text']).model_dump())
    assert response.status_code == 200
    assert response.json()['native'] == sample['native']
    assert sample['text'] not in response.text
    assert 'hash_key' not in response.text and '15485863' not in response.text

@pytest.mark.parametrize('text', ['', ' \n ', '\x00secret-marker', 'x'*20001, '\ud800'])
def test_invalid_inputs_not_echoed(api, text):
    response = api.post('/api/v1/analyze', content=json.dumps({'text':text}),headers={'Content-Type':'application/json'})
    assert response.status_code == 422
    assert 'secret-marker' not in response.text and 'input' not in response.json()

def test_request_bytes_limited_and_extra_fields_rejected(api):
    assert api.post('/api/v1/analyze',content=b'x'*131073).status_code == 413
    assert api.post('/api/v1/analyze',json={'text':'a','raw_score':100}).status_code == 422
    assert api.post('/api/v1/analyze',content=b'{bad').status_code == 422

def test_busy_api_retry(api, adapter):
    adapter._lock.acquire()
    try:
        response = api.post('/api/v1/analyze',json=payload('text').model_dump())
        assert response.status_code == 429 and response.headers['Retry-After'] == '2'
    finally:
        adapter._lock.release()

def test_samples_and_capabilities_exclude_keys_and_scores(api):
    samples = api.get('/api/v1/kgw/samples').json()
    assert len(samples) == 6
    assert 'native' not in samples[0]
    caps = api.get('/api/v1/capabilities')
    assert caps.json()['detectors'][0]['status'] == 'ready'
    assert 'hash_key' not in caps.text and '15485863' not in caps.text

def test_analysis_requires_auth_without_override():
    app = create_app(Settings(_env_file=None, supabase_url='https://example.supabase.co',supabase_publishable_key='sb_publishable_unit'))
    with TestClient(app) as client:
        assert client.post('/api/v1/analyze',json={'text':'text'}).status_code == 401
        assert client.get('/api/v1/kgw/samples').status_code == 401

def test_reduced_character_limit_and_whitespace_preservation(api):
    api.app.state.settings.analysis_max_characters = 100
    try:
        assert api.post('/api/v1/analyze',json={'text':'x'*101}).status_code == 413
    finally:
        api.app.state.settings.analysis_max_characters = 20000
    assert AnalysisInput(text='  word\n').text == '  word\n'

def test_chunked_body_limit_before_downstream_parser():
    import asyncio
    from app.core.analysis_limits import AnalysisBodyLimit
    called = False
    sent = []
    chunks = iter([{'type':'http.request','body':b'x'*70000,'more_body':True},
                   {'type':'http.request','body':b'x'*70000,'more_body':False}])
    async def downstream(*args):
        nonlocal called
        called = True
    async def receive():
        return next(chunks)
    async def send(message):
        sent.append(message)
    asyncio.run(AnalysisBodyLimit(downstream)({'type':'http','path':'/api/v1/analyze'},receive,send))
    assert not called and sent[0]['status'] == 413
