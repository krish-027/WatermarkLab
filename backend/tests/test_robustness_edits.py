"""Pure local edit tests. No detector mocks, hosted requests or semantic claims."""
import pytest
from app.services.robustness_edits import Edit, replay, transform

def test_punctuation_records_replay_original_offsets_and_preserve_source():
    source='“Hello”—she said, ‘café 🌍’.'
    result=transform(source,'minor_edit')
    assert result.text=='"Hello" - she said, \'café 🌍\'.'
    assert replay(source,result.edits)==result.text
    assert source=='“Hello”—she said, ‘café 🌍’.'

def test_synonyms_are_bounded_whole_words_case_aware_and_deterministic():
    source='LARGE small quickly important help'
    result=transform(source,'synonym',strength=50)
    assert result.text=='BIG little quickly important help'
    assert len(result.edits)==2
    assert result==transform(source,'synonym',strength=50)

def test_no_eligible_changes_is_explicit_empty_record():
    result=transform('café 中文 🌍','synonym')
    assert result.text=='café 中文 🌍' and result.edits==()

@pytest.mark.parametrize('strength,expected',[(1,'one two three four'),(50,'one two'),(100,'one')])
def test_shortening_retains_prefix_and_at_least_one_word(strength,expected):
    source='one two three four'
    result=transform(source,'shorten',strength=strength)
    assert result.text==expected and replay(source,result.edits)==expected

@pytest.mark.parametrize('source',['','  ','x'*20001,'a\x00b'])
def test_invalid_source_rejected(source):
    with pytest.raises(ValueError): transform(source,'minor_edit')

@pytest.mark.parametrize('strength',[0,101,True,1.5])
def test_invalid_strength_rejected(strength):
    with pytest.raises(ValueError): transform('text','synonym',strength=strength)

def test_tampered_and_overlapping_change_records_rejected():
    with pytest.raises(ValueError): replay('abc',(Edit(0,1,'z','x','test'),))
    with pytest.raises(ValueError): replay('abc',(Edit(0,2,'ab','x','test'),Edit(1,2,'b','y','test')))

def test_repr_does_not_expose_source_or_replacements():
    result=transform('“private-marker”','minor_edit')
    assert 'private-marker' not in repr(result)

def test_unsupported_operation_rejected():
    with pytest.raises(ValueError): transform('text','unsupported')

def test_minor_agreement_article_and_word_edits_replay():
    source='I is here in order to help. They is eating a apple.'
    result=transform(source,'minor_edit')
    assert result.text=='I am here to help. They are eating an apple.'
    assert replay(source,result.edits)==result.text
    assert len(result.edits)==4
