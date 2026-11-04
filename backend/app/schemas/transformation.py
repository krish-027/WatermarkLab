"""Ephemeral Gemini operations; no lineage/persistence or detector claims."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

Operation = Literal['paraphrase','restructure','shorten']
Objective = Literal['preserve','moderate','substantial']

class TransformInput(BaseModel):
    model_config = ConfigDict(extra='forbid',hide_input_in_errors=True)
    text: str = Field(min_length=1,max_length=4000,repr=False)
    operation: Operation = 'paraphrase'
    objective: Objective = 'preserve'
    external_processing_consent: StrictBool

    @field_validator('external_processing_consent')
    @classmethod
    def require_consent(cls,value):
        if value is not True:
            raise ValueError('Explicit consent required')
        return value

    @field_validator('text')
    @classmethod
    def valid_text(cls,value):
        if not value.strip() or '\x00' in value:
            raise ValueError('Provide nonblank text without NUL')
        try: value.encode('utf-8')
        except UnicodeEncodeError: raise ValueError('Invalid Unicode') from None
        return value

class GeneratedPayload(BaseModel):
    model_config = ConfigDict(extra='forbid',hide_input_in_errors=True)
    transformed_text: str = Field(min_length=1,max_length=8000,repr=False)
    change_summary: str = Field(min_length=1,max_length=600,repr=False)

    @field_validator('transformed_text','change_summary')
    @classmethod
    def valid_output(cls,value):
        if not value.strip() or '\x00' in value:
            raise ValueError('Blank or invalid generated text')
        value.encode('utf-8')
        return value

class Usage(BaseModel):
    input_tokens: int | None = Field(default=None,ge=0)
    output_tokens: int | None = Field(default=None,ge=0)
    thinking_tokens: int | None = Field(default=None,ge=0)
    total_tokens: int | None = Field(default=None,ge=0)

class TransformResult(BaseModel):
    transformed_text: str = Field(repr=False)
    change_summary: str = Field(repr=False)
    operation: Operation
    objective: Objective
    model: str
    model_version: str | None = None
    prompt_version: str
    generation_settings: dict
    source_characters: int
    output_characters: int
    execution_ms: float
    usage: Usage
    provenance: Literal['UNKNOWN'] = 'UNKNOWN'
    warnings: list[str]
