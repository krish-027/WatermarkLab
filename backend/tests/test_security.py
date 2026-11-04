from time import time
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import verify_token
from app.main import create_app

ISSUER = 'https://test.supabase.co/auth/v1'


@pytest.fixture
def signed():
    private = ec.generate_private_key(ec.SECP256R1())
    resolver = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key()))
    claims = dict(sub=str(uuid4()), iss=ISSUER, aud='authenticated', role='authenticated', iat=int(time()), exp=int(time()) + 60)
    def token(changes=None, key=None):
        payload = {k:v for k,v in {**claims, **(changes or {})}.items() if v is not None}
        return jwt.encode(payload, key or private, algorithm='ES256', headers={'kid': 'unit-key'})
    return resolver, claims, token


def test_real_signature_and_claims(signed):
    resolver, claims, token = signed
    assert verify_token(token(), ISSUER, resolver).user_id == claims['sub']


@pytest.mark.parametrize('change', [dict(exp=0), dict(iss='https://attacker.example/auth/v1'), dict(aud='anon'), dict(role='service_role'), dict(sub='not-uuid'), dict(iat=int(time()) + 3600), dict(is_anonymous=True)])
def test_rejects_invalid_claims(signed, change):
    resolver, _, token = signed
    with pytest.raises(jwt.InvalidTokenError):
        verify_token(token(change), ISSUER, resolver)


def test_rejects_wrong_signature(signed):
    resolver, _, token = signed
    other = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(jwt.InvalidSignatureError):
        verify_token(token(key=other), ISSUER, resolver)


@pytest.mark.parametrize('claim', ['exp','iat','iss','aud','sub','role'])
def test_requires_all_identity_claims(signed, claim):
    resolver, _, token = signed
    with pytest.raises(jwt.InvalidTokenError):
        verify_token(token({claim: None}), ISSUER, resolver)


def test_rejects_unsigned_and_symmetric_tokens(signed):
    resolver, claims, _ = signed
    for algorithm, key in [('none', ''), ('HS256', 'x' * 32)]:
        token = jwt.encode(claims, key, algorithm=algorithm, headers={'kid': 'unit-key'})
        with pytest.raises(jwt.InvalidTokenError):
            verify_token(token, ISSUER, resolver)


def test_missing_setup_and_missing_bearer():
    no_setup = TestClient(create_app(Settings(_env_file=None)))
    assert no_setup.get('/api/v1/me').status_code == 503
    configured = TestClient(create_app(Settings(_env_file=None, supabase_url='https://test.supabase.co', supabase_publishable_key='sb_publishable_unit_fixture')))
    assert configured.get('/api/v1/me').status_code == 401
