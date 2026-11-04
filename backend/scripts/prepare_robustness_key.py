"""Prepare a dedicated local signing key and private SQL provisioning file.

No network calls and no secret output. Run only after reviewing the migration.
The generated SQL contains a secret: use the project's SQL editor, never chat.
"""
from pathlib import Path
import secrets
import os
import re
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
env=root/'.env'
values={k.lower():v for k,v in (dotenv_values(env) if env.exists() else {}).items()}
process={k.lower():v for k,v in os.environ.items()}
for setting in ('robustness_signing_key','robustness_signing_key_id'):
    if setting in process:
        if setting in values and values[setting]!=process[setting]:
            raise SystemExit('Signing environment conflicts with .env. No changes made.')
        # Fail closed for environment-only configuration too: a different startup
        # shell could otherwise use a different key than provisioning.
        if setting not in values:
            raise SystemExit('Signing environment override requires matching .env configuration. No changes made.')
values={k.upper():v for k,v in values.items()}
key=values.get('ROBUSTNESS_SIGNING_KEY') or secrets.token_hex(32)
key_id=values.get('ROBUSTNESS_SIGNING_KEY_ID') or 'v1'
if not re.fullmatch('[0-9a-fA-F]{64}',key) or not re.fullmatch('[a-zA-Z0-9_-]{1,32}',key_id):
    raise SystemExit('Existing signing configuration is invalid; review it locally. No changes made.')
target=root/'.cache/robustness_key_setup.sql'
if target.exists():raise SystemExit('Provisioning file already exists; preserve it and review locally. No changes made.')
target.parent.mkdir(exist_ok=True)
if not values.get('ROBUSTNESS_SIGNING_KEY'):
    with env.open('a',encoding='utf-8') as handle:
        handle.write('\nROBUSTNESS_SIGNING_KEY='+key+'\nROBUSTNESS_SIGNING_KEY_ID='+key_id+'\n')
target.write_text("-- PRIVATE LOCAL KEY MATERIAL. Do not commit, log or share.\nbegin;\n"
    "insert into watermarklab_private.receipt_keys(key_id,secret) values ('"+key_id+"',decode('"+key+"','hex')) on conflict(key_id) do nothing;\n"
    "do $$ begin if not exists(select 1 from watermarklab_private.receipt_keys where key_id='"+key_id+"' and enabled and secret=decode('"+key+"','hex')) then raise exception 'Key identifier already exists with different or disabled material'; end if; end $$;\ncommit;\n",encoding='utf-8')
print('Prepared backend signing configuration and backend/.cache/robustness_key_setup.sql. Secret values suppressed. No remote operation performed.')
