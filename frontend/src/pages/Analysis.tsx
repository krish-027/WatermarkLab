import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Fingerprint, ShieldCheck } from 'lucide-react'
import { useAuth } from '../auth/AuthProvider'
import { analysisRequest, capabilitiesSchema, resultSchema, samplesSchema } from '../lib/analysis'
import type { AnalysisResult, Sample } from '../lib/analysis'

export function Evidence({ result }: { result: AnalysisResult }) {
  const synthid = result.method === 'SYNTHID'
  const count = (n: number | null) => n ?? 'Not calculated'
  const metrics: [string, string | number][] = [
    [synthid ? 'Native p-value' : 'Native z-score', synthid ? result.p_value === null ? 'Not available' : result.p_value === 0 ? '0 (underflow)' : result.p_value.toExponential(4) : result.z_score === null ? 'Not available' : result.z_score.toFixed(4)],
    ['Decision rule', result.decision_rule ?? 'Not evaluated'], ['Compatible tokens', result.token_count ?? 'Not calculated'],
    [synthid ? 'Unmasked positions' : 'Scored tokens', count(result.scored_token_count)],
    ...(synthid ? [['G-value ones / trials',`${count(result.g_value_ones)} / ${count(result.g_value_trials)}`],['Masked positions',count(result.masked_position_count)],['Repeated contexts',count(result.repeated_context_count)],['EOS-masked positions',count(result.eos_masked_position_count)]] as [string,string|number][] : [['Green tokens',count(result.green_token_count)],['Repeated pairs',count(result.repeated_pair_count)]] as [string,string|number][]),
    ['Characters', result.character_count], ['Execution', `${result.execution_ms.toFixed(1)} ms`],
  ]
  return <section className="analysis-result" aria-labelledby="evidence-title" aria-live="polite"><p className="eyebrow">NATIVE STATISTICAL EVIDENCE</p><h2 id="evidence-title">{result.verdict}</h2><p>{result.method} · <code>{result.profile_id ?? 'No compatible profile'}</code></p><dl className="evidence-grid">{metrics.map(([label,value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><p>{synthid ? 'A small p-value is evidence against the configured null model. It is not an AI-authorship probability or a population false-positive-rate guarantee. Mask counts can overlap.' : 'No native p-value is provided. The z-score is not an AI-authorship probability.'}</p><p>Provenance: <strong>{result.provenance.replaceAll('_',' ')}</strong> — {result.provenance_source}.</p><p>Compatibility: {result.compatibility_status} · {result.compatibility_basis}.</p><ul>{result.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul><details><summary>How to interpret {synthid ? 'SynthID' : 'KGW'} evidence</summary>{synthid ? <><p>This DeepMind Threefry research profile tests binary g-values recovered from compatible token ngrams. The unchanged reference returns the upper binomial tail under its null model, using EOS and repeated-context masks. The application uses p ≤ 0.01 after its screening guards.</p><p>This is not the Hugging Face sampling-table profile or production Gemini verification. The public research key and threshold have not been independently calibrated for population error rates. No Bayesian detector is used.</p></> : <p>KGW uses preceding tokens to select a pseudorandom green list, then biases those tokens during generation. Detection compares the observed green-token count with its expected count. This profile uses a strict z &gt; 4.0 threshold.</p>}<p>Short or highly repetitive text can be inconclusive even when native evidence is available. A negative result cannot establish human authorship or rule out other watermark schemes.</p></details></section>
}

export default function Analysis() {
  const { session } = useAuth()
  const [text, setText] = useState('')
  const [method, setMethod] = useState<'KGW'|'SYNTHID'>('KGW')
  const [profile, setProfile] = useState('')
  const [compatible, setCompatible] = useState(false)
  const [provenance, setProvenance] = useState('UNKNOWN')
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [sampleNote, setSampleNote] = useState('')
  const caps = useQuery({ queryKey: ['capabilities'], queryFn: async () => capabilitiesSchema.parse(await analysisRequest('capabilities')), retry: false })
  const samples = useQuery({ queryKey: ['detector-samples', method, session?.user.id], queryFn: async () => samplesSchema.parse(await analysisRequest(`${method.toLowerCase()}/samples`, session?.access_token)), retry: false, enabled: !!session })
  const selected = caps.data?.detectors.find(item => item.method === method)
  const synthid = method==='SYNTHID'
  const limit = caps.data?.max_characters ?? 20000
  function changed(next: string) { setText(next); setResult(null); setSampleNote(''); setCompatible(false); setProvenance('UNKNOWN'); setError('') }
  function loadSample(sample: Sample) { setText(sample.text); setProfile(sample.profile_id); setCompatible(true); setProvenance(sample.provenance); setSampleNote(`${sample.id}: ${sample.label_source}. Generated research text may be inaccurate; not a benchmark.`); setResult(null); setError('') }
  async function upload(file?: File) {
    if (!file) return
    if (!/\.(txt|md)$/i.test(file.name) || file.size > 80000) { setError('Choose a UTF-8 .txt or .md file no larger than 80 KB.'); return }
    try {
      const content = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer())
      if (Array.from(content).length > limit || content.includes('\0')) throw new Error('limit')
      changed(content)
    } catch { setError(`File must be valid UTF-8, contain no NUL characters and have at most ${limit} characters.`) }
  }
  async function analyze() {
    if (!text.trim()) { setError('Enter text or choose a known sample first.'); return }
    if (Array.from(text).length > limit) { setError(`Use at most ${limit} characters.`); return }
    setBusy(true); setError(''); setResult(null)
    try { setResult(resultSchema.parse(await analysisRequest('analyze', session?.access_token, { text, method, profile_id: profile || null, compatibility_confirmed: compatible, provenance }))) }
    catch(error) { setError(error instanceof Error && !error.message.includes('[') ? error.message : 'Unexpected analysis response. Check the local API and retry.') }
    finally { setBusy(false) }
  }
  return <div className="container page-shell"><p className="eyebrow">WATERMARK ANALYSIS</p><h1>Examine the signal.</h1><p className="page-intro">Test a known compatible research profile and inspect its native evidence. This is not a general AI-text detector.</p><Link className="inline-link" to="/dashboard">← Research overview</Link> · <Link className="inline-link" to="/transform">Gemini transformations →</Link><div className="analysis-layout"><section className="analysis-editor"><label>Detector method<select value={method} disabled={busy} onChange={e => { setMethod(e.target.value as 'KGW'|'SYNTHID'); setProfile(''); setCompatible(false); setProvenance('UNKNOWN'); setResult(null); setSampleNote(''); setError('') }}><option value="KGW">KGW — Green-list watermark</option><option value="SYNTHID">SynthID Text — DeepMind frequentist research</option></select></label><h2><Fingerprint size={22} aria-hidden="true" />{synthid ? 'SynthID Text · Tournament watermark' : 'KGW · Green-list watermark'}</h2>{caps.isPending ? <p role="status">Checking detector setup…</p> : caps.isError ? <p role="alert">Cannot check detector availability. <button className="text-button" onClick={() => void caps.refetch()}>Retry availability</button></p> : <p><strong>{selected?.status ?? 'unavailable'}</strong> — {selected?.message ?? 'No verified profile is available.'}</p>}
    <fieldset disabled={busy}><legend>Compatible configuration</legend><label>{synthid ? 'SynthID profile' : 'KGW profile'}<select value={profile} onChange={e => { setProfile(e.target.value); setCompatible(false); setResult(null) }}><option value="">Unknown / no matching profile</option>{synthid ? <option value="synthid-threefry-gpt2-cpu-v1">DeepMind Threefry GPT-2 · CPU research profile v1</option> : <option value="kgw-gpt2-cpu-v1">KGW GPT-2 · pinned CPU research profile v1</option>}</select></label><p>{synthid ? 'Pinned GPT-2 tokenizer · CPU · Threefry · 5-token ngram · depth 30 · history 1024 · p ≤ 0.01. Continuation text only; remove the prompt. Public research preset only. Hugging Face, Bayesian and production Gemini profiles are unsupported.' : 'GPT-2 tokenizer · CPU · gamma 0.5 · delta 2 · one-token context · time/left scheme · z > 4.0. This matches only the supplied research preset, not arbitrary KGW configurations.'}</p><label className="checkbox-label"><input type="checkbox" checked={compatible} disabled={!profile} onChange={e => { setCompatible(e.target.checked); setResult(null) }} />I have matching generation metadata for this exact profile.</label><label>Provenance declaration<select value={provenance} onChange={e => { setProvenance(e.target.value); setResult(null) }}><option value="UNKNOWN">Unknown provenance</option><option value="KNOWN_WATERMARKED">Known watermarked (declared)</option><option value="KNOWN_UNWATERMARKED">Known unwatermarked (declared)</option></select></label></fieldset>
    <div className="sample-picker"><h3>Controlled research samples</h3><p>Real locally generated pairs. Loading a sample fills its recorded profile and label; analysis runs afresh.</p>{samples.isPending ? <p role="status">Loading sample metadata…</p> : samples.isError ? <p>Samples unavailable. <button className="text-button" onClick={() => void samples.refetch()}>Retry samples</button></p> : <label>Load a known sample<select value="" disabled={busy} onChange={e => { const sample = samples.data?.find(s => s.id === e.target.value); if (sample) loadSample(sample) }}><option value="">Choose a sample…</option>{samples.data?.map(s => <option key={s.id} value={s.id}>{s.id} · {s.provenance.replaceAll('_',' ')}</option>)}</select></label>}</div>
    <label>Text to analyze<textarea rows={13} value={text} disabled={busy} onChange={e => changed(e.target.value)} placeholder="Paste compatible text, or load a controlled sample above." /></label><p className="text-count">{Array.from(text).length.toLocaleString()} / {limit.toLocaleString()} characters · {text.trim() ? text.trim().split(/\s+/u).length : 0} whitespace-separated words · tokenizer count appears after analysis · profile limit {Math.min(caps.data?.max_tokens ?? 4096, selected?.max_tokens ?? 4096)} tokens</p>{sampleNote && <p className="sample-note">{sampleNote}</p>}<label className="upload-label">Upload UTF-8 text (.txt / .md, up to 80 KB)<input type="file" accept=".txt,.md,text/plain,text/markdown" disabled={busy} onChange={e => { void upload(e.target.files?.[0]); e.target.value = '' }} /></label><div className="hero-actions"><button className="button button-primary" disabled={busy || caps.isPending || caps.isError || selected?.status !== 'ready'} onClick={() => void analyze()}>{busy ? 'Analyzing locally…' : synthid ? 'Analyze SynthID' : 'Analyze KGW'}</button><button className="button button-secondary" disabled={busy} onClick={() => { changed(''); setProfile('') }}>Clear text</button></div>{busy && <p role="status">Running the reference detector. Text is not saved.</p>}{error && <p role="alert" className="field-error">{error}</p>}</section>
    <aside className="analysis-aside"><ShieldCheck size={24} aria-hidden="true" /><h2>Evidence with context</h2><p>Text is sent only to your configured local API. It is not saved to Supabase or sent to Gemini. Results stay in this page until cleared or navigation.</p><p>Unknown compatibility returns INCONCLUSIVE. At least 50 {synthid ? 'unmasked positions' : 'scored tokens'} are required by this app’s screening policy; longer text does not guarantee a reliable decision.</p><p>Match tokenizer, reference version, CPU profile and watermark settings. A provenance declaration is separate from the result.</p><Link className="inline-link" to="/documentation#methodology">Read methodology →</Link></aside></div>{result ? <Evidence result={result} /> : <div className="analysis-empty">No evidence yet. Choose a compatible sample and run analysis.</div>}</div>
}
