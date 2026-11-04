"""Thin adapter over unchanged, pinned MarkLLM. No model weights or network I/O."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
from threading import Lock
from time import perf_counter

from app.core.config import BACKEND_ROOT
from app.schemas.analysis import AnalysisInput, AnalysisResult

PROFILE_ID = 'kgw-gpt2-cpu-v1'
SOURCE_REVISION = '0a4fe8c642b31b8a8c4993615b1c70a0c300d918'
MODEL_REVISION = '607a30d783dfa663caf39e06633721c8d4cfcd7e'
REFERENCE = BACKEND_ROOT / 'third_party/markllm'
ASSETS = BACKEND_ROOT / '.cache/kgw-gpt2'
ASSET_HASHES = {
    'config.json': '0daed7749b4f02b8f76240d5444551d7b08712dab4d0adb8239c56ba823bb7b4',
    'tokenizer.json': '8414cab924d8b9b33013f0d221c5862f365ee9be39c5c2bfae8a5a9e970478a6',
    'tokenizer_config.json': '5e04eb606e3a1583530a42e36c2a6b6615c86f34fe77e44d9ddeb43ff940931f',
    'vocab.json': '196139668be63f3b5d6574427317ae82f612a97c5d1cdaf36ed2256dbf636783',
    'merges.txt': '1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5',
}
LIMITATIONS = [
    'Tests only this compatible KGW profile; not general AI-text detection.',
    'A negative result does not prove human authorship or absence of other watermarks.',
    'MarkLLM counts repeated contexts; the z-score null approximation assumes conditions that arbitrary text may violate.',
    'No native p-value is supplied. The 50-scored-token guard is a local screening policy, not a reliability guarantee.',
]

class KGWAdapter:
    def __init__(self, assets: Path = ASSETS):
        self.assets = assets
        self._lock = Lock()  # MarkLLM owns a mutable RNG; serialize scoring and initialization.
        self._detector = None
        self._tokenizer = None

    def _load(self):
        if self._detector is not None:
            return
        for package, version in [('torch', '2.7.1+cpu'), ('transformers', '4.57.6'), ('tokenizers', '0.22.2')]:
            if importlib.metadata.version(package) != version:
                raise RuntimeError('Unverified dependency version')
        for name, digest in ASSET_HASHES.items():
            if hashlib.sha256((self.assets / name).read_bytes()).hexdigest() != digest:
                raise RuntimeError('Tokenizer profile mismatch')
        manifest = json.loads((REFERENCE / 'SHA256SUMS.json').read_text())
        for name, digest in manifest.items():
            if hashlib.sha256((REFERENCE / name).read_bytes()).hexdigest() != digest:
                raise RuntimeError('Reference source mismatch')
        if str(REFERENCE) not in sys.path:
            sys.path.insert(0, str(REFERENCE))
        import torch
        from transformers import AutoTokenizer
        from utils.transformers_config import TransformersConfig
        from watermark.kgw.kgw import KGW
        torch.set_num_threads(2)
        tokenizer = AutoTokenizer.from_pretrained(self.assets, local_files_only=True, use_fast=True, trust_remote_code=False)
        if len(tokenizer) != 50257:
            raise RuntimeError('Vocabulary mismatch')
        detector = KGW(str(REFERENCE / 'config/KGW.json'), TransformersConfig(None, tokenizer, device='cpu'))
        self._tokenizer, self._detector = tokenizer, detector

    def capabilities(self):
        with self._lock:
            try:
                self._load()
                status, message = 'ready', 'Pinned CPU tokenizer and reference implementation loaded; no model weights needed for detection.'
            except Exception:
                status, message = 'setup required', 'Install backend/requirements-kgw.txt and run scripts/setup_kgw.py; verify the pinned versions and assets, then restart the API.'
        return dict(method='KGW', status=status, message=message, profile_id=PROFILE_ID,
                    model='openai-community/gpt2', tokenizer_revision=MODEL_REVISION,
                    reference_revision=SOURCE_REVISION, device='cpu', vocabulary_size=50257,
                    gamma=0.5, delta=2.0, prefix_length=1, f_scheme='time', window_scheme='left',
                    threshold=4.0, decision_rule='z > 4.0', minimum_scored_tokens=50,
                    warnings=LIMITATIONS)

    def analyze(self, payload: AnalysisInput, max_tokens: int = 4096) -> AnalysisResult:
        start = perf_counter()
        result = AnalysisResult(method=payload.method, profile_id=payload.profile_id,
                                verdict='INCONCLUSIVE', provenance=payload.provenance,
                                character_count=len(payload.text))
        def finish():
            result.execution_ms = round((perf_counter() - start) * 1000, 3)
            return result
        if payload.method != 'KGW':
            result.verdict = 'UNAVAILABLE'
            result.warnings = ['This adapter evaluates KGW only; select the separate SynthID adapter for compatible SynthID profiles.']
            return finish()
        if payload.profile_id != PROFILE_ID or not payload.compatibility_confirmed:
            result.compatibility_status = 'unsupported' if payload.profile_id not in (None, PROFILE_ID) else 'unknown'
            result.warnings = ['Select the exact compatible profile and confirm matching generation metadata. Unknown compatibility cannot be scored.']
            return finish()
        result.compatibility_status = 'declared'
        if not self._lock.acquire(blocking=False):
            # Route maps this to a retryable 429; do not accumulate CPU jobs.
            raise BlockingIOError('Detector busy')
        try:
            try:
                self._load()
            except Exception:
                result.verdict = 'UNAVAILABLE'
                result.warnings = ['KGW setup is missing, incompatible or failed to load. Check optional dependencies and pinned tokenizer assets.']
                return finish()
            ids = self._tokenizer(payload.text, add_special_tokens=False, truncation=False, verbose=False)['input_ids']
            result.token_count = len(ids)
            result.scored_token_count = max(0, len(ids) - 1)
            result.threshold = 4.0
            result.decision_rule = 'z > 4.0'
            result.warnings = list(LIMITATIONS)
            if len(ids) > max_tokens:
                result.warnings.insert(0, f'Input exceeds the {max_tokens}-token limit; no truncation or scoring was performed.')
                return finish()
            if len(ids) <= 1:
                result.warnings.insert(0, 'No token remains after the required one-token prefix.')
                return finish()
            # Run the actual native entrypoint; visualization is a second reference
            # pass used for counts. Tests independently verify their z formula.
            native = self._detector.detect_watermark(payload.text)
            flags = self._detector.get_data_for_visualization(payload.text).highlight_values
            result.native = native
            result.raw_score = result.z_score = native['score']
            result.green_token_count = flags.count(1)
            pairs = list(zip(ids, ids[1:]))
            result.repeated_pair_count = len(pairs) - len(set(pairs))
            if result.scored_token_count < 50:
                result.warnings.insert(0, 'Too short for the local 50-scored-token policy; native evidence is descriptive only.')
            elif result.repeated_pair_count > len(pairs) / 2:
                result.warnings.insert(0, 'Most context/token pairs repeat. Native evidence is unreliable for this text; decision withheld.')
            else:
                result.verdict = 'DETECTED' if native['is_watermarked'] else 'NOT DETECTED'
            return finish()
        except Exception:
            # Do not expose exception text, paths or submitted text to clients/logs.
            result.verdict = 'UNAVAILABLE'
            result.native = None
            result.raw_score = result.z_score = None
            result.warnings = ['The reference detector could not evaluate this input. Retry or check the local setup.']
            return finish()
        finally:
            self._lock.release()
