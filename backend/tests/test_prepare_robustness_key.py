"""Provisioning script runs only against temporary files, never real .env."""
import subprocess
import sys
from pathlib import Path
from dotenv import dotenv_values
import os
import pytest

@pytest.mark.parametrize('mode',['matching','conflicting_key','conflicting_id','environment_only'])
def test_environment_configuration_is_consistent_or_fails_closed(tmp_path,mode):
    scripts=tmp_path/'scripts';scripts.mkdir()
    script=scripts/'prepare_robustness_key.py'
    script.write_bytes((Path(__file__).parents[1]/'scripts/prepare_robustness_key.py').read_bytes())
    key='ab'*32
    original='' if mode=='environment_only' else 'ROBUSTNESS_SIGNING_KEY='+key+'\nROBUSTNESS_SIGNING_KEY_ID=v1\n'
    (tmp_path/'.env').write_text(original)
    environment={k:v for k,v in os.environ.items() if not k.lower().startswith('robustness_signing_')}
    environment.update(ROBUSTNESS_SIGNING_KEY='cd'*32 if mode=='conflicting_key' else key,ROBUSTNESS_SIGNING_KEY_ID='v2' if mode=='conflicting_id' else 'v1')
    result=subprocess.run([sys.executable,str(script)],env=environment,capture_output=True,text=True)
    assert (result.returncode==0)==(mode=='matching')
    assert key not in result.stdout+result.stderr
    assert (tmp_path/'.env').read_text()==original
    assert (tmp_path/'.cache/robustness_key_setup.sql').exists()==(mode=='matching')

def test_provisioning_is_local_secret_safe_and_preserves_configuration(tmp_path):
    scripts=tmp_path/'scripts';scripts.mkdir()
    script=scripts/'prepare_robustness_key.py'
    script.write_bytes((Path(__file__).parents[1]/'scripts/prepare_robustness_key.py').read_bytes())
    (tmp_path/'.env').write_text('EXISTING_SETTING=preserved\n')
    first=subprocess.run([sys.executable,str(script)],capture_output=True,text=True)
    assert first.returncode==0
    values=dotenv_values(tmp_path/'.env');key=values['ROBUSTNESS_SIGNING_KEY']
    assert len(key)==64 and values['EXISTING_SETTING']=='preserved'
    assert key not in first.stdout+first.stderr
    assert key in (tmp_path/'.cache/robustness_key_setup.sql').read_text()
    second=subprocess.run([sys.executable,str(script)],capture_output=True,text=True)
    assert second.returncode!=0 and key not in second.stdout+second.stderr
    assert dotenv_values(tmp_path/'.env')==values
