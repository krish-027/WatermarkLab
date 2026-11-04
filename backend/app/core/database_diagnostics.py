"""Bounded, allowlisted failure metadata. Never store upstream error text."""
import json

HEADER='X-WatermarkLab-Database-Diagnostic'
REQUEST_HEADER='X-WatermarkLab-Diagnostics'
LIMIT=4096
CODES=frozenset({'42501','22023','23514','23503','23505','42702','42883','42P01','28000','PGRST202','PGRST203','PGRST204','PGRST205','PGRST301','PGRST302'})
STAGES=frozenset({'save_rpc','readback'})

def parse_http_error(error,stage):
    code=None
    try:
        raw=error.read(LIMIT+1)
        if len(raw)<=LIMIT:
            body=json.loads(raw)
            candidate=body.get('code') if isinstance(body,dict) else None
            if isinstance(candidate,str) and candidate in CODES:code=candidate
    except Exception:
        pass  # Diagnostics must never change the public error behavior.
    status=error.code if type(error.code) is int and 100<=error.code<=599 else None
    stage=stage if isinstance(stage,str) and stage in STAGES else None
    return {'upstream_http_status':status,'database_stage':stage,'postgrest_code':code,
            'sqlstate':code if code and len(code)==5 else None,
            'rpc_function':'save_robustness_run' if stage=='save_rpc' else None}

def development_headers(request,error,stage):
    settings=request.app.state.settings
    # Dedicated local Python runner only; no browser/CORS diagnostic channel.
    if (settings.app_env!='development' or not settings.database_diagnostics_enabled
        or not request.client or request.client.host not in ('127.0.0.1','::1')
        or request.headers.get('origin') is not None
        or request.headers.get(REQUEST_HEADER)!='1'):
        return None
    return {HEADER:json.dumps(parse_http_error(error,stage),separators=(',',':'))}
