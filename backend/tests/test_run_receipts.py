import copy
import json
import pytest
from app.services.run_receipts import issue,verify,commitment,signing_key

OWNER='11111111-1111-4111-8111-111111111111'
KEY='ab'*32  # Public unit fixture, never a production secret.

def run():
    evidence={'method':'KGW','profile_id':'kgw-gpt2-cpu-v1','verdict':'DETECTED','provenance':'UNKNOWN','token_count':101,'scored_token_count':100,'execution_ms':1.,'character_count':500,'z_score':5.,'p_value':None,'threshold':4.}
    return {'status':'completed','experiment_id':'22222222-2222-4222-8222-222222222222','transformation':{'operation':'synonym','strength':25,'objective':'preserve'},'original':{'id':'33333333-3333-4333-8333-333333333333','parent_sample_id':None,'text':'private original','detection':evidence},'child':{'id':'44444444-4444-4444-8444-444444444444','parent_sample_id':'33333333-3333-4333-8333-333333333333','text':'private child','detection':evidence}}

def test_receipt_is_bound_to_owner_and_expiry_without_text():
    receipt=issue(run(),OWNER,KEY,now=100)
    assert verify(receipt,OWNER,KEY,now=101)['id']==run()['experiment_id']
    assert 'private original' not in json.dumps(receipt)
    with pytest.raises(ValueError): verify(receipt,OWNER,KEY,now=1900)
    with pytest.raises(ValueError): verify(receipt,'other',KEY,now=101)

@pytest.mark.parametrize('field',['id','owner','operation','strength'])
def test_tampering_rejected(field):
    receipt=issue(run(),OWNER,KEY,now=100)
    body=json.loads(receipt['payload']);body[field]='tampered';receipt['payload']=json.dumps(body)
    with pytest.raises(ValueError):verify(receipt,OWNER,KEY,now=101)

def test_text_commitment_bound_to_sample_and_exact_text():
    key=signing_key(KEY)
    assert commitment(key,'e','a','text')!=commitment(key,'e','b','text')
    assert commitment(key,'e','a','text')!=commitment(key,'e','a','text ')

def test_keys_fail_closed():
    with pytest.raises(ValueError):issue(run(),OWNER,'')
    receipt=issue(run(),OWNER,KEY,now=100)
    with pytest.raises(ValueError):verify(receipt,OWNER,'cd'*32,now=101)

def test_receipt_excludes_edit_fragments_and_bounds_metadata():
    value=run();value['transformation']['edits']=[{'start':0,'end':3,'rule':'word','before':'private','after':'secret'}]
    receipt=issue(value,OWNER,KEY)
    assert json.loads(receipt['payload'])['edits']==[{'start':0,'end':3,'rule':'word'}]
    assert 'private' not in receipt['payload'] and 'secret' not in receipt['payload']
    value['transformation']['edits']*=2000
    with pytest.raises(ValueError):issue(value,OWNER,KEY)
