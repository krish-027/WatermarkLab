"""Credential-safe hosted pytest entry point: never emit captured failure objects."""
import contextlib
import io
import json
import os
import re
import sys

from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
try:
    from scripts.hosted_diagnostics import CODES, sanitize
except ModuleNotFoundError:
    from hosted_diagnostics import CODES, sanitize


class SafeResults:
    def __init__(self):
        self.results = []

    def pytest_runtest_logreport(self, report):
        if report.when == 'call' or report.failed or report.skipped:
            item = {'test': report.nodeid, 'stage': report.when, 'outcome': report.outcome}
            if report.failed:
                diagnostic = str(report.longrepr)
                for message in ['Real sign-in failed', 'Migration/grants', 'Profile migration/grants', 'Test accounts must be independent']:
                    if message in diagnostic:
                        item['diagnostic'] = message
                        break
                comparison = re.search(r'assert (\d{3}) == (\d{3})', diagnostic)
                if comparison:
                    item['actual_http_status'], item['expected_http_status'] = comparison.groups()
                denial = re.search(r'DENIAL_STATUS=(\d{3});CODE=([A-Z0-9]{5,10})',diagnostic)
                if denial:
                    item['denial_status']=denial.group(1)
                    item['database_code']=denial.group(2) if denial.group(2) in CODES else None
                item.setdefault('diagnostic', 'Assertion or request failure; raw details suppressed')
            item['http_diagnostics']=[sanitize(v) for k,v in getattr(report,'user_properties',[]) if k=='safe_http_diagnostic']
            self.results.append(item)


if __name__ == '__main__':
    if os.getenv('WATERMARKLAB_LIVE_TESTS') != '1':
        raise SystemExit('Explicit WATERMARKLAB_LIVE_TESTS=1 required')
    os.environ['WATERMARKLAB_SAFE_HOSTED_RUNNER'] = '1'
    plugin = SafeResults()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        targets=sys.argv[1:] or ['tests/test_supabase_live.py']
        if any(not re.fullmatch(r'tests/test_(?:supabase_live|robustness_live)\.py(?:::[A-Za-z0-9_]+)?',target) for target in targets):
            raise SystemExit('Only hosted test node IDs are allowed')
        code = pytest.main([*targets, '-q', '-x', '--tb=no', '--show-capture=no', '-rN', '-p', 'no:cacheprovider'], plugins=[plugin])
    print(json.dumps({'exit_code': int(code), 'results': plugin.results}))
    raise SystemExit(code)
