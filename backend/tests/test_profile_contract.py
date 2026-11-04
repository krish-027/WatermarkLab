"""Local API payload/upsert contract only; not an authentication integration test."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.routes import accounts
from app.core.security import Identity


def test_profile_is_atomically_created_for_verified_identity(monkeypatch):
    user_id=str(uuid4())
    captured={}
    def database(request, identity, path, method, payload, prefer):
        captured.update(path=path,method=method,payload=payload,prefer=prefer)
        return [payload]
    monkeypatch.setattr(accounts,'database',database)
    result=accounts.save_profile(accounts.ProfileInput(display_name='Researcher'),SimpleNamespace(),Identity(user_id,'unit-token'))
    assert result=={'id':user_id,'display_name':'Researcher','retain_text':False}
    assert captured['path']=='profiles?on_conflict=id'
    assert captured['method']=='POST'
    assert 'resolution=merge-duplicates' in captured['prefer']


def test_profile_does_not_accept_browser_owner_id():
    with pytest.raises(ValidationError):
        accounts.ProfileInput(display_name='test',id=str(uuid4()))
