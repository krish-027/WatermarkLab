import json
from app.core.database_diagnostics import CODES, HEADER, STAGES as DATABASE_STAGES
"""Test reporting only: fixed vocabularies, never echo provider messages."""
STAGES={'compare','save_endpoint','readback','profile','identity','cleanup'}
DETAILS={
 'Unknown receipt key':'receipt_key_unknown',
 'Receipt invalid, expired or signing setup unavailable':'receipt_rejected',
 'Text retention requires explicit consent for both samples':'retention_input_rejected',
 'Database access denied':'database_access_denied',
 'Database request failed. Check migration and grants.':'database_request_failed',
 'Database unavailable':'database_unavailable',
 'Save acknowledgement could not be verified; retry manually with the same receipt':'readback_failed',
}
CATEGORIES=set(DETAILS.values())|{'unknown','http_success','http_error','request_failed'}

def sanitize(value):
    value=value if isinstance(value,dict) else {}
    value={k:v for k,v in value.items() if isinstance(v,(str,int)) and not isinstance(v,bool)}
    status=value.get('http_status')
    return {'http_status':status if type(status) is int and 100<=status<=599 else None,
      'upstream_http_status':value.get('upstream_http_status') if type(value.get('upstream_http_status')) is int and 100<=value['upstream_http_status']<=599 else None,
      'database_stage':value.get('database_stage') if value.get('database_stage') in DATABASE_STAGES else None,
      'request_stage':value.get('request_stage') if value.get('request_stage') in STAGES else None,
      'application_code':value.get('application_code') if value.get('application_code') in CATEGORIES else None,
      'postgrest_code':value.get('postgrest_code') if isinstance(value.get('postgrest_code'),str) and value.get('postgrest_code') in CODES else None,
      'sqlstate':value.get('sqlstate') if isinstance(value.get('sqlstate'),str) and value.get('sqlstate') in CODES and len(value['sqlstate'])==5 else None,
      'rpc_function':'save_robustness_run' if value.get('rpc_function')=='save_robustness_run' else None}

def response_diagnostic(response,stage):
    try:body=response.json()
    except Exception:body={}
    body=body if isinstance(body,dict) else {}
    detail=body.get('detail')
    upstream={}
    try:
        encoded=response.headers.get(HEADER,'')
        if len(encoded)<=1024:
            parsed=json.loads(encoded)
            if isinstance(parsed,dict):upstream=parsed
    except (ValueError,TypeError):pass
    upstream=sanitize(upstream)
    return sanitize({**{k:upstream[k] for k in ('upstream_http_status','database_stage','postgrest_code','sqlstate','rpc_function')},'http_status':response.status_code,'request_stage':stage,
      'application_code':DETAILS.get(detail,'http_success' if response.status_code<400 else 'http_error') if isinstance(detail,str) else ('http_success' if response.status_code<400 else 'http_error')})
