import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app(Settings(_env_file=None)))


def test_health_without_external_credentials(client, monkeypatch):
    for key in ('GEMINI_API_KEY', 'GEMINI_MODEL', 'SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY'):
        monkeypatch.delenv(key, raising=False)
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'service': 'watermarklab-api', 'version': '0.2.0'}


def test_swagger_and_openapi_describe_only_implemented_routes(client):
    assert client.get('/docs').status_code == 200
    schema = client.get('/openapi.json').json()
    assert '/health' in schema['paths']
    assert '/api/v1/me' in schema['paths']
    assert '/api/v1/analyze' in schema['paths']
    assert client.post('/api/v1/analyze', json={'text': 'example'}).status_code == 503


def test_allowed_origin_receives_cors_header(client):
    response = client.get('/health', headers={'Origin': 'http://localhost:5173'})
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'


def test_untrusted_origin_receives_no_permission(client):
    response = client.get('/health', headers={'Origin': 'https://untrusted.example'})
    assert 'access-control-allow-origin' not in response.headers


def test_preflight_rejects_untrusted_origin_and_mutating_method(client):
    for origin, method in [('https://untrusted.example', 'GET'), ('http://localhost:5173', 'TRACE')]:
        response = client.options('/health', headers={
            'Origin': origin, 'Access-Control-Request-Method': method,
        })
        assert response.status_code == 400


@pytest.mark.parametrize('origin', ['*', '', 'https://host/path', 'https://user:password@host', 'ftp://host', 'https://host:bad'])
def test_invalid_cors_configuration_rejected(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=origin)


def test_comma_separated_cors_and_port_validation():
    settings = Settings(_env_file=None, cors_origins='http://localhost:5173, http://127.0.0.1:5173')
    assert settings.allowed_origins == ['http://localhost:5173', 'http://127.0.0.1:5173']
    with pytest.raises(ValidationError):
        Settings(_env_file=None, backend_port=70000)
