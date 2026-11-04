"""Real CPU detector comparisons; local identity override, no hosted requests."""
import json
from fastapi.testclient import TestClient
from app.core.config import Settings, BACKEND_ROOT
from app.core.security import Identity, require_user
from app.main import create_app
import pytest

@pytest.fixture(scope='module')
def client():
    app=create_app(Settings(_env_file=None))
    app.dependency_overrides[require_user]=lambda:Identity('local-test','not-a-real-token')
    with TestClient(app) as client: yield client

@pytest.mark.parametrize('method,profile',[('KGW','kgw-gpt2-cpu-v1'),('SYNTHID','synthid-threefry-gpt2-cpu-v1')])
def test_real_fixed_profile_pair_and_lineage(client,method,profile):
    samples=json.loads((BACKEND_ROOT/f'research/{method.lower()}_pilot.json').read_text())['samples']
    source=next(r['text'] for r in samples if r['provenance']=='KNOWN_WATERMARKED' and (method=='KGW' or r.get('implementation')=='deepmind-threefry'))
    response=client.post('/api/v1/compare',json={'text':source,'method':method,'profile_id':profile,'compatibility_confirmed':True,'provenance':'KNOWN_WATERMARKED','operation':'shorten','strength':25})
    assert response.status_code==200
    data=response.json()
    assert data['original']['text']==source
    assert data['child']['parent_sample_id']==data['original']['id']
    assert data['child']['id']!=data['original']['id']
    before,after=data['original']['detection'],data['child']['detection']
    assert before['verdict']=='DETECTED'
    assert before['profile_id']==after['profile_id']==profile
    assert before['threshold']==after['threshold']
    assert after['provenance']=='UNKNOWN'
    assert data['semantic']['score'] is None
    assert data['comparison']['character_delta']<0
    assert response.headers['cache-control']=='no-store'

def test_unsupported_profile_never_becomes_negative_or_calls_google(client):
    result=client.post('/api/v1/compare',json={'text':'Some text','profile_id':'unsupported','compatibility_confirmed':True,'operation':'paraphrase','external_processing_consent':True}).json()
    assert result['status']=='not_run' and result['baseline']['verdict']=='INCONCLUSIVE'

def test_private_route_and_safe_invalid_body():
    with TestClient(create_app(Settings(_env_file=None,supabase_url='https://example.supabase.co',supabase_publishable_key='sb_publishable_unit'))) as client:
        assert client.post('/api/v1/compare',json={'text':'hello'}).status_code==401
        assert client.post('/api/v1/compare',content=b'x'*131073).status_code==413

def test_validation_omits_private_input(client):
    result=client.post('/api/v1/compare',json={'text':'private-marker','strength':0})
    assert result.status_code==422 and 'private-marker' not in result.text
