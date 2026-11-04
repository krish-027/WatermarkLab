import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { transformRequest } from '../lib/transformations'
import { samplesSchema, resultSchema } from '../lib/analysis'
import { Evidence } from './Analysis'
import { z } from 'zod'

const sample=z.object({id:z.string(),parent_sample_id:z.string().nullable(),text:z.string(),detection:resultSchema})
const completed=z.object({status:z.literal('completed'),experiment_id:z.string(),original:sample,child:sample,transformation:z.object({operation:z.string(),strength:z.number(),objective:z.string(),edits:z.array(z.object({start:z.number(),end:z.number(),before:z.string(),after:z.string(),rule:z.string()})),provider:z.unknown().nullable()}),comparison:z.object({evidence_field:z.string(),delta:z.number().nullable(),comparable:z.boolean(),character_delta:z.number(),token_delta:z.number().nullable(),decision_changed:z.boolean().nullable()}),warnings:z.array(z.string()),receipt:z.object({payload:z.string(),signature:z.string(),key_id:z.string()}).nullable()})
type Run=z.infer<typeof completed>

export default function Robustness(){
 const {session}=useAuth()
 const [text,setText]=useState(''),[method,setMethod]=useState('KGW'),[confirmed,setConfirmed]=useState(false)
 const [operation,setOperation]=useState('minor_edit'),[strength,setStrength]=useState(25),[objective,setObjective]=useState('preserve')
 const [consent,setConsent]=useState(false),[saveConsent,setSaveConsent]=useState(false),[retain,setRetain]=useState(false)
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[run,setRun]=useState<Run|null>(null),[saveStatus,setSaveStatus]=useState('Unsaved')
 const [samples,setSamples]=useState<z.infer<typeof samplesSchema>>([]),[provenance,setProvenance]=useState('UNKNOWN')
 const [meaning,setMeaning]=useState('not_reviewed'),[omissions,setOmissions]=useState('not_reviewed'),[facts,setFacts]=useState('not_reviewed')
 const external=operation==='paraphrase'||operation==='restructure'
 const profile=method==='KGW'?'kgw-gpt2-cpu-v1':'synthid-threefry-gpt2-cpu-v1'
 function reset(){setRun(null);setConsent(false);setSaveConsent(false);setRetain(false);setSaveStatus('Unsaved');setMeaning('not_reviewed');setOmissions('not_reviewed');setFacts('not_reviewed');setError('')}
 async function load(){setError('');try{setSamples(samplesSchema.parse(await transformRequest(method==='KGW'?'kgw/samples':'synthid/samples',session?.access_token)))}catch{setError('Could not load controlled samples. Check your session and local setup.')}}
 async function compare(){
  if(!text.trim()){setError('Enter source text.');return}
  if(external&&!consent){setError('Consent to Google processing before this request.');return}
  setBusy(true);setRun(null);setError('');setSaveStatus('Unsaved');setSaveConsent(false)
  try{
   const data=await transformRequest('compare',session?.access_token,{text,method,profile_id:profile,compatibility_confirmed:confirmed,provenance,operation,strength,objective,external_processing_consent:consent})
   if(data.status==='not_run'){const baseline=resultSchema.parse(data.baseline);setError(`${baseline.verdict}: ${data.message}`)}
   else {setRun(completed.parse(data));setMeaning('not_reviewed');setOmissions('not_reviewed');setFacts('not_reviewed')}
  }catch{setError('Comparison failed. Check configuration and limits. A completed Google request may have consumed quota; do not retry automatically.')}
  finally{setBusy(false);setConsent(false)}
 }
 async function save(){
  if(!run?.receipt||!saveConsent||saveStatus==='Saved and read back')return
  setBusy(true);setSaveStatus('Saving')
  try{const result=await transformRequest('robustness/runs',session?.access_token,{...run.receipt,save_consent:true,manual_review:{meaning,omissions,facts},retain_text:retain,original_text:retain?run.original.text:null,child_text:retain?run.child.text:null});if(result.status!=='saved')throw new Error();setSaveStatus('Saved and read back')}
  catch{setSaveStatus('Save failed. Check migration, signing-key setup, receipt expiry and retention preference. Retry the same receipt; no Gemini request is made.')}
  finally{setBusy(false)}
 }
 return <div className="container page-shell robustness-page"><p className="eyebrow">ROBUSTNESS LAB · PHASE 7 DEVELOPMENT</p><h1>Compare a controlled edit.</h1><p className="page-intro">One paired observation under a fixed research profile. Reduced evidence does not prove watermark removal or preserved meaning.</p><Link to="/dashboard">Research overview</Link>
 <section className="analysis-editor"><fieldset disabled={busy}><legend>Original and transformation</legend>
 <label>Detector<select aria-label="Detector" value={method} onChange={e=>{setMethod(e.target.value);setSamples([]);setConfirmed(false);setProvenance('UNKNOWN');reset()}}><option>KGW</option><option>SYNTHID</option></select></label><p>Fixed profile: {profile}</p>
 <button className="button button-secondary" onClick={()=>void load()}>Load controlled samples</button><label>Controlled sample<select aria-label="Controlled sample" defaultValue="" onChange={e=>{const s=samples.find(s=>s.id===e.target.value);if(s){reset();setText(s.text);setProvenance(s.provenance);setConfirmed(true)}}}><option value="">Choose a sample</option>{samples.map(s=><option key={s.id} value={s.id}>{s.id}</option>)}</select></label>
 <label>Original text<textarea aria-label="Original text" rows={9} value={text} onChange={e=>{setText(e.target.value);setConfirmed(false);setProvenance('UNKNOWN');reset()}}/></label><p>{Array.from(text).length} characters · provenance {provenance}</p>
 <label><input type="checkbox" checked={confirmed} onChange={e=>{setConfirmed(e.target.checked);reset()}}/>I confirm that the original matches this exact research profile. This is a declaration, not independent proof.</label>
 <label>Transformation<select value={operation} onChange={e=>{setOperation(e.target.value);reset()}}><option value="minor_edit">Minor deterministic editing</option><option value="synonym">Fixed-lexicon substitution</option><option value="shorten">Deterministic shortening</option><option value="paraphrase">Gemini paraphrase</option><option value="restructure">Gemini sentence restructuring</option></select></label>
 {!external&&operation!=='minor_edit'&&<label>Strength (1–100)<input type="number" min={1} max={100} value={strength} onChange={e=>{setStrength(Number(e.target.value));reset()}}/></label>}
 {external&&<><label>Objective<select value={objective} onChange={e=>{setObjective(e.target.value);reset()}}><option value="preserve">High preservation objective</option><option value="moderate">Moderate rewriting</option><option value="substantial">Substantial restructuring</option></select></label><p>Google receives source text and editing instructions. This may use paid quota. No automatic retries. See <Link to="/transform">Gemini prompt and settings</Link>.</p><label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>I consent to sending this text to Google for this request.</label></>}
 </fieldset><div className="hero-actions"><button className="button button-primary" disabled={busy} onClick={()=>void compare()}>{busy?'Working…':'Run paired comparison'}</button><button className="button button-secondary" disabled={busy} onClick={()=>{setText('');setConfirmed(false);setProvenance('UNKNOWN');reset()}}>Clear experiment</button></div>{error&&<p role="alert">{error}</p>}</section>
 {run&&<><p>Experiment {run.experiment_id} · original {run.original.id} → child {run.child.id} · parent {run.child.parent_sample_id}</p><div className="analysis-layout">{([['Original',run.original],['Child',run.child]] as const).map(([title,s])=><section className="analysis-editor" key={title}><h2>{title}</h2><textarea aria-label={`${title} result text`} readOnly rows={10} value={s.text}/><Evidence result={s.detection}/></section>)}</div>
 <section className="analysis-result"><h2>Observed change</h2><p>{run.comparison.evidence_field} delta (child − original): {run.comparison.delta??'Unavailable: comparison inconclusive'}. Character change: {run.comparison.character_delta}. Token change: {run.comparison.token_delta??'Unavailable'}.</p><p>Decision changed: {run.comparison.decision_changed===null?'Inconclusive':String(run.comparison.decision_changed)}. For KGW lower z indicates weaker evidence; for SynthID higher p indicates weaker evidence. Scales are not interchangeable.</p><details><summary>Auditable edit records and settings</summary><pre className="transform-pre">{JSON.stringify(run.transformation,null,2)}</pre></details>{run.warnings.map(w=><p key={w}>{w}</p>)}</section>
 <section className="analysis-result"><h2>Manual semantic review</h2><p>Automatic similarity: unavailable; no embedding model installed. Manual judgments are not measured equivalence.</p>{([['Meaning preserved',meaning,setMeaning],['Omissions present',omissions,setOmissions],['Factual changes present',facts,setFacts]] as const).map(([label,value,set])=><label key={label}>{label}<select aria-label={label} disabled={busy||saveStatus==='Saved and read back'} value={value} onChange={e=>set(e.target.value)}><option value="not_reviewed">Not reviewed</option><option value="yes">Yes, in my assessment</option><option value="no">No, in my assessment</option><option value="uncertain">Uncertain</option></select></label>)}<p>Review names, quantities, negations and removed claims in the texts above. Categorical review answers are saved only when you explicitly save the experiment. They remain user judgments.</p></section>
 <section className="analysis-result"><h2>Opt-in saving · verification pending</h2><p>Metadata excludes text and edit fragments. Receipt expires after 30 minutes. Retaining both texts additionally requires your profile retention preference. Review categories are saved separately from signed detector evidence.</p><label><input type="checkbox" disabled={busy||saveStatus==='Saved and read back'} checked={saveConsent} onChange={e=>setSaveConsent(e.target.checked)}/>Save this experiment's signed metadata and evidence.</label><label><input type="checkbox" disabled={busy||saveStatus==='Saved and read back'} checked={retain} onChange={e=>setRetain(e.target.checked)}/>Also retain both original and child text.</label><button className="button button-primary" disabled={busy||!saveConsent||!run.receipt||saveStatus==='Saved and read back'} onClick={()=>void save()}>Save experiment</button><p role="status">{run.receipt?saveStatus:'Saving unavailable: signing setup required.'}</p></section></>}
 </div>
}
