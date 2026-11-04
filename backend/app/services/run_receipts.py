"""Backend-issued metadata receipts. Never sign client-submitted results."""
import hashlib
import hmac
import json
import re
import time
from uuid import UUID

FIELDS=('method','profile_id','verdict','provenance','token_count','character_count',
        'z_score','p_value','threshold','scored_token_count','g_value_ones','g_value_trials',
        'green_token_count','repeated_pair_count','masked_position_count','repeated_context_count','eos_masked_position_count','execution_ms')

def signing_key(value):
    if not re.fullmatch('[0-9a-fA-F]{64}',value):
        raise ValueError('Configure a 32-byte hexadecimal robustness signing key')
    return bytes.fromhex(value)

def commitment(key,experiment_id,sample_id,text):
    return hmac.new(key,('text-v1\n'+experiment_id+'\n'+sample_id+'\n'+text).encode(),hashlib.sha256).hexdigest()

def issue(run,owner,key_hex,key_id='v1',now=None):
    key=signing_key(key_hex)
    UUID(owner)
    if run['status']!='completed': raise ValueError('Only completed runs may be signed')
    timestamp=int(time.time() if now is None else now)
    payload={'v':1,'owner':owner,'id':run['experiment_id'],'issued':timestamp,'expires':timestamp+1800,
             'operation':run['transformation']['operation'],'strength':run['transformation']['strength'],
             'objective':run['transformation']['objective'],'transform_version':run['transformation'].get('version','unspecified'),'generation':None,'samples':[],
             'edits':[{k:e[k] for k in ('start','end','rule')} for e in run['transformation'].get('edits',[])]}
    provider=run['transformation'].get('provider')
    if provider:
        payload['generation']={k:provider.get(k) for k in ('model','model_version','prompt_version','usage','generation_settings')}
    for name in ('original','child'):
        sample=run[name]
        payload['samples'].append({'id':sample['id'],'parent':sample['parent_sample_id'],
            'text_mac':commitment(key,run['experiment_id'],sample['id'],sample['text']),
            'evidence':{k:sample['detection'].get(k) for k in FIELDS}})
    encoded=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    if len(encoded.encode('utf-8'))>32768:raise ValueError('Receipt exceeds save metadata limit')
    signature=hmac.new(key,('receipt-v1\n'+key_id+'\n'+encoded).encode(),hashlib.sha256).hexdigest()
    return {'payload':encoded,'signature':signature,'key_id':key_id}

def verify(receipt,owner,key_hex,now=None):
    key=signing_key(key_hex)
    expected=hmac.new(key,('receipt-v1\n'+receipt['key_id']+'\n'+receipt['payload']).encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,receipt['signature']): raise ValueError('Invalid receipt')
    value=json.loads(receipt['payload'])
    timestamp=int(time.time() if now is None else now)
    if value['owner']!=owner or value['v']!=1 or not value['issued']<=timestamp<value['expires']:
        raise ValueError('Invalid or expired receipt')
    return value
