import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Sparkles, ExternalLink } from 'lucide-react'
import { useAuth } from '../auth/AuthProvider'
import { transformRequest,transformCapabilities,transformResult } from '../lib/transformations'
import type { TransformResult } from '../lib/transformations'

export default function Transform() {
  const {session}=useAuth()
  const [text,setText]=useState('')
  const [operation,setOperation]=useState('paraphrase')
  const [objective,setObjective]=useState('preserve')
  const [consent,setConsent]=useState(false)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [result,setResult]=useState<TransformResult|null>(null)
  const caps=useQuery({queryKey:['gemini-capabilities'],queryFn:async()=>transformCapabilities.parse(await transformRequest('transform/capabilities')),retry:false})
  function edit(next:string) {setText(next);setResult(null);setConsent(false);setError('')}
  async function submit() {
    if(!text.trim()) {setError('Enter source text first.');return}
    if(Array.from(text).length>(caps.data?.max_characters??4000)) {setError('Use at most 4,000 characters.');return}
    if(!consent) {setError('Confirm that this text may be sent to Google before submitting.');return}
    setBusy(true);setError('');setResult(null)
    try {setResult(transformResult.parse(await transformRequest('transform',session?.access_token,{text,operation,objective,external_processing_consent:true})))}
    catch(error) {setError(error instanceof Error && !error.message.includes('[')?error.message:'Unexpected response. Check the local API and retry manually.')}
    finally {setBusy(false);setConsent(false)}
  }
  return <div className="container page-shell"><p className="eyebrow">GEMINI TRANSFORMATIONS</p><h1>Explore a different phrasing.</h1><p className="page-intro">Request a controlled rewrite through Google Gemini. Review the generated text yourself; no watermark generation, detection or removal claim is made.</p><Link className="inline-link" to="/dashboard">← Research overview</Link><div className="analysis-layout"><section className="analysis-editor"><h2><Sparkles size={22} aria-hidden="true" />Controlled text transformation</h2>
    {caps.isPending?<p role="status">Checking local Gemini setup…</p>:caps.isError?<p role="alert">Cannot check setup. <button className="text-button" onClick={()=>void caps.refetch()}>Retry setup</button></p>:<p><strong>{caps.data?.status}</strong> — {caps.data?.message}</p>}
    <fieldset disabled={busy}><legend>Transformation request</legend><label>Operation<select value={operation} onChange={e=>{setOperation(e.target.value);setObjective('preserve');setResult(null);setConsent(false)}}><option value="paraphrase">Paraphrase</option><option value="restructure">Sentence restructuring</option><option value="shorten">Shorten text</option></select></label>
    {operation==='paraphrase'&&<label>Rewriting objective<select value={objective} onChange={e=>{setObjective(e.target.value);setResult(null);setConsent(false)}}><option value="preserve">High semantic preservation (objective)</option><option value="moderate">Moderate rewriting</option><option value="substantial">Substantial restructuring</option></select></label>}
    <p>{caps.data?.operations[operation]} {operation==='paraphrase'?caps.data?.objectives[objective]:''}</p>
    <label>Source text<textarea rows={11} value={text} onChange={e=>edit(e.target.value)} placeholder="Enter text you are permitted to share with Google." /></label><p className="text-count">{Array.from(text).length.toLocaleString()} / 4,000 characters · source stays editable after the request</p>
    <label className="checkbox-label"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)} />I consent to sending this text to Google Gemini for this request, which may use paid API quota.</label></fieldset>
    <div className="hero-actions"><button className="button button-primary" disabled={busy||caps.isPending||caps.isError||caps.data?.status!=='configured'} onClick={()=>void submit()}>{busy?'Requesting transformation…':'Send to Gemini'}</button><button className="button button-secondary" disabled={busy} onClick={()=>edit('')}>Clear source and result</button></div>
    {busy&&<p role="status">Waiting for Google. No automatic retries. A timed-out request may still use provider tokens.</p>}{error&&<p role="alert" className="field-error">{error}</p>}</section>
    <aside className="analysis-aside"><ExternalLink size={24} aria-hidden="true" /><h2>External processing</h2><p>Only the source text and transformation instructions go to Google’s external API. Your Supabase session and watermark configuration are not sent.</p><p>WatermarkLab does not save source text or results. Google’s data handling depends on your API account and terms. Do not submit private material without permission.</p><p>Configured model: <strong>{caps.data?.model??'Setup required'}</strong>. No automatic fallback.</p><p>Output watermark provenance stays UNKNOWN. Public SynthID detection does not verify arbitrary Gemini output. Linked before/after experiments and semantic scoring are not part of this page.</p>
    {caps.data&&<details><summary>Inspect prompt and settings before sending</summary><p>{caps.data.system_instruction}</p><p>Prompt version: {caps.data.prompt_version}</p><pre className="transform-pre">{JSON.stringify(caps.data.generation_settings,null,2)}</pre></details>}</aside></div>
    {result?<section className="analysis-result" aria-live="polite"><p className="eyebrow">GENERATED TEXT · MANUAL REVIEW REQUIRED</p><h2>Transformation returned</h2><p>{result.model} · version {result.model_version??'not supplied'} · {result.operation} · {result.execution_ms.toFixed(0)} ms</p><label>Generated text<textarea rows={10} readOnly value={result.transformed_text} aria-label="Generated text" /></label><h3>Model-reported change summary</h3><p className="transform-pre">{result.change_summary}</p><p>{result.source_characters} source characters → {result.output_characters} output characters. Watermark provenance: UNKNOWN.</p><h3>Provider-reported token usage</h3><p>Input: {result.usage.input_tokens??'Unavailable'} · Output: {result.usage.output_tokens??'Unavailable'} · Thinking: {result.usage.thinking_tokens??'Unavailable'} · Total: {result.usage.total_tokens??'Unavailable'}</p><ul>{result.warnings.map(w=><li key={w}>{w}</li>)}</ul><p>Source remains above for manual inspection. No semantic metric or detector comparison was calculated.</p></section>:<div className="analysis-empty">No transformation yet. Google is contacted only after an explicit consented submission.</div>}</div>
}
