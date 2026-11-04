"""Local mocked orchestration tests. No server, credentials or database access."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import test_robustness_live as hosted
import test_supabase_live as auth


@pytest.mark.parametrize('outcome', [
    'success', 'denied', 'transport', 'cleanup_failure', 'retained_preflight',
    'compare_transport_before', 'compare_transport_after_creation', 'compare_missing_id',
    'compare_bad_id', 'compare_null_id', 'compare_nonstring_id', 'compare_invalid_json',
    'compare_nonobject', 'compare_noncanonical_id',
])
def test_diagnostic_exact_requests_and_cleanup(monkeypatch, tmp_path, outcome):
    (tmp_path / 'research').mkdir()
    (tmp_path / 'research/kgw_pilot.json').write_text(json.dumps({
        'samples': [{'provenance': 'KNOWN_WATERMARKED', 'text': 'synthetic fixture'}]}))
    monkeypatch.setattr(hosted, 'BACKEND_ROOT', tmp_path)
    monkeypatch.setattr(hosted, 'test_hosted_robustness_persistence', lambda *a: pytest.fail('Full workflow invoked'))
    calls = []
    simulated_created = set()
    identifier = '11111111-1111-4111-8111-111111111111'

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, path, headers, json):
            calls.append((method, path, json))
            assert headers['Authorization'] == 'Bearer dummy-A'
            assert method != 'PUT'
            if path.endswith('/me'): return httpx.Response(200, json={'id': 'owner-A'})
            if path.endswith('/profile'): return httpx.Response(200, json={'id': 'owner-A', 'retain_text': True})
            if path.endswith('/compare'):
                assert json['method'] == 'KGW' and json['operation'] == 'shorten'
                if outcome == 'compare_transport_after_creation':
                    # Hypothetical server-contract violation: no client ID is recoverable.
                    simulated_created.add(identifier)
                    raise RuntimeError('private-marker')
                if outcome == 'compare_transport_before': raise RuntimeError('private-marker')
                if outcome == 'compare_invalid_json': return httpx.Response(200, content=b'private-marker')
                if outcome == 'compare_nonobject': return httpx.Response(200, json=[])
                if outcome == 'compare_missing_id': return httpx.Response(200, json={'receipt': {}})
                if outcome.startswith('compare_'):
                    bad_id = {'compare_bad_id': 'private-marker?broad-filter', 'compare_null_id': None,
                              'compare_nonstring_id': 123, 'compare_noncanonical_id': identifier.replace('-', '')}[outcome]
                    return httpx.Response(200, json={'experiment_id': bad_id})
                return httpx.Response(200, json={'experiment_id': identifier, 'receipt': {'payload': 'private-marker', 'signature': 'private-marker'}})
            if path.endswith('/robustness/runs'):
                assert json['retain_text'] is False and json['save_consent'] is True
                assert json['original_text'] is None and json['child_text'] is None
                if outcome == 'transport': raise RuntimeError('private-marker')
                if outcome == 'denied':
                    return httpx.Response(503, headers={'X-WatermarkLab-Database-Diagnostic':
                        '{"upstream_http_status":403,"database_stage":"save_rpc","postgrest_code":"42501","sqlstate":"42501"}'},
                        json={'detail': 'Database request failed. Check migration and grants.'})
                return httpx.Response(200, json={'status': 'saved'})
            assert method == 'DELETE' and path == '/api/v1/experiments/' + identifier
            simulated_created.discard(identifier)
            return httpx.Response(500 if outcome == 'cleanup_failure' else 204)

    reads = []
    def db(path, token):
        assert token == 'dummy-A'
        reads.append(path)
        assert path in ('/rest/v1/experiment_samples?raw_text=not.is.null&select=id&limit=1',
                        '/rest/v1/experiments?id=eq.' + identifier)
        return 200, ([{'id': 'existing'}] if outcome == 'retained_preflight' else [])

    monkeypatch.setattr(hosted.httpx, 'Client', Client)
    request = SimpleNamespace(node=SimpleNamespace(user_properties=[]))
    if outcome == 'success':
        hosted.test_hosted_robustness_save_diagnostic_only((None, db, [('owner-A', 'dummy-A')]), request)
    else:
        with pytest.raises(AssertionError) as error:
            hosted.test_hosted_robustness_save_diagnostic_only((None, db, [('owner-A', 'dummy-A')]), request)
        if outcome.startswith('compare_'):
            assert str(error.value).startswith('Diagnostic cleanup failed or unverified')
    expected = [('GET', '/api/v1/me'), ('GET', '/api/v1/profile')]
    if outcome != 'retained_preflight':
        expected += [('POST', '/api/v1/compare')]
        if not outcome.startswith('compare_'):
            expected += [('POST', '/api/v1/robustness/runs'), ('DELETE', '/api/v1/experiments/' + identifier)]
            assert reads[-1] == '/rest/v1/experiments?id=eq.' + identifier
    assert [(m, p) for m, p, _ in calls] == expected
    report = json.loads((tmp_path / '.cache/phase7_save_diagnostic_results.json').read_text())
    assert report['comparison_requests'] == (0 if outcome == 'retained_preflight' else 1)
    assert report['save_requests'] == (0 if outcome == 'retained_preflight' or outcome.startswith('compare_') else 1)
    assert 'private-marker' not in json.dumps(report) + json.dumps(request.node.user_properties)
    if outcome == 'denied':
        failure = next(d for d in report['http_diagnostics'] if d['request_stage'] == 'save_endpoint')
        assert failure['http_status'] == 503 and failure['sqlstate'] == '42501'
    if outcome.startswith('compare_'):
        assert report['cleanup'] == {'status': 'unverified', 'own_experiment_absent': None}
        assert len(reads) == 1  # Only the retained-text preflight; no speculative ID lookup.
        assert simulated_created == ({identifier} if outcome == 'compare_transport_after_creation' else set())
    elif outcome != 'retained_preflight':
        assert report['cleanup']['own_experiment_absent'] == (outcome != 'cleanup_failure')
        assert report['cleanup']['status'] == ('failed' if outcome == 'cleanup_failure' else 'verified')
    else:
        assert report['cleanup'] == {'status': 'not_required', 'own_experiment_absent': None}


def test_account_a_fixture_uses_only_a(monkeypatch):
    labels_seen = []
    def shared(labels):
        labels_seen.append(labels)
        yield 'fixture'
    monkeypatch.setattr(auth, '_live_accounts', shared)
    assert list(auth.live_a.__wrapped__()) == ['fixture']
    assert labels_seen == [('A',)]


def test_diagnostic_node_independently_collectable():
    node = 'tests/test_robustness_live.py::test_hosted_robustness_save_diagnostic_only'
    env = dict(os.environ, WATERMARKLAB_LIVE_TESTS='0', WATERMARKLAB_SAFE_HOSTED_RUNNER='0',
               WATERMARKLAB_PHASE7_PERSISTENCE_TESTS='0', WATERMARKLAB_LOCAL_SQL='0')
    result = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', node],
                            cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    assert node in result.stdout and '1 test collected' in result.stdout
    assert '::test_hosted_robustness_persistence' not in result.stdout
