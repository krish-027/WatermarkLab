"""Deterministic, auditable edits; no assertion of semantic preservation.

Offsets refer to Python Unicode code points in the original source. Operations
never mutate the source or use a language model. Each record can be replayed.
"""
from dataclasses import dataclass, field
import re
from typing import Literal

Operation = Literal['minor_edit', 'synonym', 'shorten']
VERSION = 'deterministic-edits-v2'
# Small explicit research lexicon, intentionally not a universal thesaurus.
SYNONYMS = {'large':'big', 'small':'little', 'quick':'rapid', 'begin':'start',
            'important':'significant', 'help':'assist', 'often':'frequently'}

@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    before: str = field(repr=False)
    after: str = field(repr=False)
    rule: str

@dataclass(frozen=True)
class EditedText:
    text: str = field(repr=False)
    edits: tuple[Edit, ...]
    operation: str
    version: str = VERSION

def replay(source: str, edits: tuple[Edit, ...]) -> str:
    cursor = 0
    pieces = []
    for edit in edits:
        if not cursor <= edit.start <= edit.end <= len(source):
            raise ValueError('Invalid or overlapping edit offsets')
        if source[edit.start:edit.end] != edit.before:
            raise ValueError('Edit does not match its source')
        pieces.extend((source[cursor:edit.start], edit.after))
        cursor = edit.end
    pieces.append(source[cursor:])
    return ''.join(pieces)

def transform(source: str, operation: Operation, *, strength: int = 25) -> EditedText:
    if not isinstance(source,str) or not source.strip() or len(source)>20000 or '\x00' in source:
        raise ValueError('Invalid source text')
    source.encode('utf-8')
    if type(strength) is not int or not 1 <= strength <= 100:
        raise ValueError('Strength must be an integer from 1 to 100')
    edits = []
    if operation == 'minor_edit':
        # Change typography only; never silently claim grammar correction.
        replacements = {'“':'"','”':'"','‘':"'",'’':"'",'—':' - '}
        for match in re.finditer('[“”‘’—]',source):
            edits.append(Edit(match.start(),match.end(),match.group(),replacements[match.group()],'typographic punctuation'))
        rules=[(r'\bI is\b','I am','fixed agreement edit'),
               (r'\bThey is\b','They are','fixed agreement edit'),
               (r'\bthey is\b','they are','fixed agreement edit'),
               (r'\bin order to\b','to','minor phrase simplification'),
               (r'\ba apple\b','an apple','fixed article edit')]
        for pattern,replacement,rule in rules:
            for match in re.finditer(pattern,source):
                edits.append(Edit(match.start(),match.end(),match.group(),replacement,rule+'; manually review context'))
        edits.sort(key=lambda e:e.start)
    elif operation == 'synonym':
        candidates = [m for m in re.finditer(r'\b[A-Za-z]+\b',source) if m.group().lower() in SYNONYMS]
        # Strength is a deterministic prefix fraction of eligible words, not random sampling.
        count = (len(candidates)*strength+99)//100
        for match in candidates[:count]:
            word = match.group()
            replacement = SYNONYMS[word.lower()]
            if word.isupper(): replacement = replacement.upper()
            elif word[0].isupper(): replacement = replacement.capitalize()
            edits.append(Edit(match.start(),match.end(),word,replacement,'fixed lexicon; meaning may change'))
    elif operation == 'shorten':
        # Remove a suffix at whitespace-word boundaries, retaining at least one word.
        words = list(re.finditer(r'\S+',source))
        keep = max(1, (len(words)*(100-strength)+99)//100)
        if keep < len(words):
            start = words[keep-1].end()
            edits.append(Edit(start,len(source),source[start:],'','suffix deletion; omissions expected'))
    else:
        raise ValueError('Unsupported deterministic operation')
    records = tuple(edits)
    return EditedText(replay(source,records), records, operation)
