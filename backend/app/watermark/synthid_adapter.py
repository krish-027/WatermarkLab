"""Pinned DeepMind frequentist detector; CPU/tokenizer only, no generation."""
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys
from threading import Lock
from time import perf_counter

from app.core.config import BACKEND_ROOT
from app.schemas.analysis import AnalysisInput, AnalysisResult
# Shared, exactly matching GPT-2 tokenizer assets only; no KGW algorithm calls.
from app.watermark.kgw_adapter import ASSETS, ASSET_HASHES, MODEL_REVISION

PROFILE_ID = 'synthid-threefry-gpt2-cpu-v1'
SOURCE_REVISION = '9c055d932e042b75197e337371448a120bbc65bb'
REFERENCE = BACKEND_ROOT / 'third_party/synthid'
ALPHA = 0.01
MAX_TOKENS = 1024
MIN_SCORED = 50
LIMITATIONS = [
    'Public DeepMind Threefry research profile only; not production Gemini verification or the Hugging Face sampling-table profile.',
    'Native p-value is a binomial tail under the reference null model, not an AI-authorship probability.',
    'The fixed public key and alpha=0.01 are not independently calibrated population error rates.',
    'At least 50 unmasked positions are required by this application policy; this is not a published reliability guarantee.',
    'Use continuation text only, with prompt removed. Match tokenizer, source, hash, key and mask configuration.',
    'A negative result does not prove human authorship or absence of other watermarks.',
]

class SynthIDAdapter:
    def __init__(self, assets: Path = ASSETS, reference: Path = REFERENCE):
        self.assets, self.reference = assets, reference
        self._lock = Lock()
        self._tokenizer = self._processor = self._detector = None

    def _load(self):
        if self._detector is not None:
            return
        for package, version in [('torch','2.7.1+cpu'),('transformers','4.57.6'),
                                 ('tokenizers','0.22.2'),('scipy','1.18.1'),('numpy','2.5.4')]:
            if importlib.metadata.version(package) != version:
                raise RuntimeError('Unverified dependency version')
        for name,digest in ASSET_HASHES.items():
            if hashlib.sha256((self.assets/name).read_bytes()).hexdigest() != digest:
                raise RuntimeError('Tokenizer does not match the profile')
        manifest = json.loads((self.reference/'SHA256SUMS.json').read_text())
        for name,digest in manifest.items():
            if hashlib.sha256((self.reference/name).read_bytes()).hexdigest() != digest:
                raise RuntimeError('Reference source mismatch')
        if (self.reference/'commit.txt').read_text().strip() != SOURCE_REVISION:
            raise RuntimeError('Reference revision mismatch')
        if str(self.reference) not in sys.path:
            sys.path.insert(0,str(self.reference))
        import torch
        from transformers import AutoTokenizer
        from synthid_text import detector_frequentist, logits_processing, hashing_function
        # Also verify any already-imported module, e.g. in a research/test process.
        for module in (detector_frequentist,logits_processing,hashing_function):
            name='synthid_text/'+Path(module.__file__).name
            if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != manifest[name]:
                raise RuntimeError('Cached source does not match the profile')
        torch.set_num_threads(2)
        tokenizer = AutoTokenizer.from_pretrained(self.assets,local_files_only=True,
                                                   use_fast=True,trust_remote_code=False)
        if len(tokenizer)!=50257 or tokenizer.eos_token_id!=50256:
            raise RuntimeError('Vocabulary/EOS mismatch')
        processor = logits_processing.SynthIDLogitsProcessor(ngram_len=5,key=654,depth=30,
            context_history_size=1024,device=torch.device('cpu'),skip_first_ngram_calls=True,num_leaves=2)
        self._tokenizer, self._processor = tokenizer, processor
        self._detector = detector_frequentist.FrequentistDetector(processor,eos_token_id=50256)

    def capabilities(self):
        with self._lock:
            try:
                self._load()
                status,message='ready','Pinned DeepMind frequentist research core and CPU tokenizer loaded. No model weights required.'
            except Exception:
                status,message='setup required','Install the existing KGW pins plus requirements-synthid.txt, run scripts/setup_kgw.py for the shared GPT-2 tokenizer, then restart the API.'
        return dict(method='SYNTHID',status=status,message=message,profile_id=PROFILE_ID,
            model='openai-community/gpt2',tokenizer_revision=MODEL_REVISION,reference_revision=SOURCE_REVISION,
            device='cpu',hash_scheme='Threefry 2x32',ngram_len=5,depth=30,context_history_size=1024,
            skip_first_ngram_calls=True,num_leaves=2,threshold=ALPHA,decision_rule='p <= 0.01',
            minimum_scored_tokens=MIN_SCORED,max_tokens=MAX_TOKENS,warnings=LIMITATIONS)

    def analyze(self, payload: AnalysisInput, max_tokens: int = 4096) -> AnalysisResult:
        start=perf_counter()
        result=AnalysisResult(method='SYNTHID',profile_id=payload.profile_id,verdict='INCONCLUSIVE',
                              provenance=payload.provenance,character_count=len(payload.text))
        def finish():
            result.execution_ms=round((perf_counter()-start)*1000,3)
            return result
        if payload.method!='SYNTHID' or payload.profile_id!=PROFILE_ID:
            result.compatibility_status='unsupported' if payload.profile_id else 'unknown'
            result.warnings=['Unsupported or unknown SynthID profile. Only the pinned DeepMind Threefry CPU research profile is supported; Hugging Face, Bayesian and production Gemini profiles are not supported.']
            return finish()
        if not payload.compatibility_confirmed:
            result.warnings=['Matching continuation/tokenizer/source/configuration metadata must be confirmed before scoring.']
            return finish()
        result.compatibility_status='declared'
        if not self._lock.acquire(blocking=False):
            raise BlockingIOError('Detector busy')
        try:
            try:
                self._load()
            except Exception:
                result.verdict='UNAVAILABLE'
                result.warnings=['SynthID setup is missing, incompatible or failed to load. Verify the pinned core, dependencies and tokenizer assets.']
                return finish()
            import torch
            ids=self._tokenizer(payload.text,add_special_tokens=False,truncation=False,verbose=False)['input_ids']
            result.token_count=len(ids)
            result.threshold=ALPHA
            result.decision_rule='p <= 0.01'
            result.warnings=list(LIMITATIONS)
            limit=min(max_tokens,MAX_TOKENS)
            if len(ids)>limit:
                result.warnings.insert(0,f'Input exceeds the {limit}-token SynthID profile limit; no truncation or scoring performed. This keeps context-history coverage valid.')
                return finish()
            tensor=torch.tensor([ids],dtype=torch.long,device='cpu')
            with torch.inference_mode():
                g,mask=self._processor.compute_g_values_and_mask(tensor,eos_token_id=50256)
                p=float(self._detector.p_value(tensor)[0])  # Actual native entrypoint, unchanged math.
                if not math.isfinite(p) or not 0<=p<=1:
                    raise RuntimeError('Invalid native p-value')
                scored=int(mask.sum())
                ones=int((g*mask.unsqueeze(-1)).sum())
                result.scored_token_count=scored
                result.g_value_ones=ones
                result.g_value_trials=scored*30
                result.masked_position_count=max(0,len(ids)-4)-scored
                result.repeated_context_count=int((~self._processor.compute_context_repetition_mask(tensor)).sum())
                result.eos_masked_position_count=int((~self._processor.compute_eos_token_mask(tensor,50256)[:,4:]).sum())
            result.p_value=p
            result.native={'p_value':p}
            if scored<MIN_SCORED:
                result.warnings.insert(0,'Too short after EOS/repeated-context masking for the local 50-unmasked-position policy; native p-value is descriptive only.')
            else:
                result.verdict='DETECTED' if p<=ALPHA else 'NOT DETECTED'
            if p==0:
                result.warnings.insert(0,'Native p-value underflowed to zero in floating-point arithmetic; this is not certainty of authorship.')
            return finish()
        except Exception:
            # Discard partial evidence; never echo raw input or exception messages.
            result=AnalysisResult(method='SYNTHID',profile_id=payload.profile_id,verdict='UNAVAILABLE',
                provenance=payload.provenance,character_count=len(payload.text),
                compatibility_status='declared',warnings=['The reference detector could not evaluate this input. Retry or check local setup.'])
            return finish()
        finally:
            self._lock.release()
