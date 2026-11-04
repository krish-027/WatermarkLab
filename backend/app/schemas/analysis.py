"""Ephemeral analysis contract. No client-supplied scores, keys or owner IDs."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Provenance = Literal['KNOWN_WATERMARKED', 'KNOWN_UNWATERMARKED', 'UNKNOWN']

class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    text: str = Field(min_length=1, max_length=20000, repr=False)
    method: Literal['KGW', 'SYNTHID'] = 'KGW'
    profile_id: str | None = Field(default=None, max_length=100)
    compatibility_confirmed: bool = False
    provenance: Provenance = 'UNKNOWN'

    @field_validator('text')
    @classmethod
    def valid_text(cls, value: str) -> str:
        if not value.strip() or '\x00' in value:
            raise ValueError('Provide nonblank text without NUL characters')
        try:
            value.encode('utf-8')
        except UnicodeEncodeError:
            raise ValueError('Text must be valid Unicode') from None
        return value  # Whitespace is tokenization-relevant; never silently normalize.

class AnalysisResult(BaseModel):
    method: str
    profile_id: str | None
    verdict: Literal['DETECTED', 'NOT DETECTED', 'INCONCLUSIVE', 'UNAVAILABLE']
    provenance: Provenance
    provenance_source: str = 'user declaration; not independently verified'
    compatibility_basis: str = 'user declaration; not independently verified'
    compatibility_status: Literal['unknown', 'declared', 'unsupported'] = 'unknown'
    character_count: int
    token_count: int | None = None
    scored_token_count: int | None = None
    green_token_count: int | None = None
    repeated_pair_count: int | None = None
    raw_score: float | None = None
    z_score: float | None = None
    p_value: float | None = Field(default=None, ge=0, le=1)
    g_value_ones: int | None = None
    g_value_trials: int | None = None
    masked_position_count: int | None = None
    repeated_context_count: int | None = None
    eos_masked_position_count: int | None = None
    threshold: float | None = None
    decision_rule: str | None = None
    native: dict[str, float | bool] | None = None
    execution_ms: float = 0
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def separate_evidence(self):
        if self.method == 'SYNTHID' and any(value is not None for value in
                (self.raw_score, self.z_score, self.green_token_count, self.repeated_pair_count)):
            raise ValueError('SynthID does not supply KGW evidence')
        if self.method == 'KGW' and any(value is not None for value in
                (self.p_value, self.g_value_ones, self.g_value_trials, self.masked_position_count,
                 self.repeated_context_count, self.eos_masked_position_count)):
            raise ValueError('KGW does not supply SynthID evidence')
        return self
