// UI transport/auth mocks only; actual CPU/hosted-browser checks are separate.
import {render,screen,waitFor} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {MemoryRouter} from 'react-router-dom'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {test,expect,vi,beforeEach} from 'vitest'
import Robustness from '../pages/Robustness'

vi.mock('../auth/AuthProvider',()=>({useAuth:()=>({session:{access_token:'unit'}})}))
const baseline={method:'KGW',profile_id:null,verdict:'INCONCLUSIVE',provenance:'UNKNOWN',provenance_source:'unit declaration',compatibility_basis:'unknown',character_count:12,token_count:null,scored_token_count:null,green_token_count:null,repeated_pair_count:null,raw_score:null,z_score:null,p_value:null,threshold:null,decision_rule:null,execution_ms:1,warnings:[],native:null}
beforeEach(()=>vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({status:'not_run',baseline,message:'Compatible profile required.'})})))
function show(){return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><Robustness/></MemoryRouter></QueryClientProvider>)}

test('empty source cannot submit',async()=>{
 show();await userEvent.click(screen.getByRole('button',{name:'Run paired comparison'}))
 expect(screen.getByRole('alert')).toHaveTextContent('Enter source text')
 expect(fetch).not.toHaveBeenCalled()
})
test('Gemini requires explicit consent and no automatic request',async()=>{
 show();await userEvent.type(screen.getByLabelText('Original text'),'Example text')
 await userEvent.selectOptions(screen.getByLabelText('Transformation'),'paraphrase')
 await userEvent.click(screen.getByRole('button',{name:'Run paired comparison'}))
 expect(screen.getByRole('alert')).toHaveTextContent('Consent')
 expect(fetch).not.toHaveBeenCalled()
})
test('unsupported baseline remains inconclusive without a child',async()=>{
 show();await userEvent.type(screen.getByLabelText('Original text'),'Example text')
 await userEvent.click(screen.getByRole('button',{name:'Run paired comparison'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('INCONCLUSIVE')
 expect(screen.queryByRole('heading',{name:'Observed change'})).toBeNull()
 expect(fetch).toHaveBeenCalledTimes(1)
})
test('request failure enables manual retry without fabricated evidence',async()=>{
 vi.mocked(fetch).mockRejectedValue(new Error('offline'))
 show();await userEvent.type(screen.getByLabelText('Original text'),'Example text')
 await userEvent.click(screen.getByRole('button',{name:'Run paired comparison'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('Comparison failed')
 await waitFor(()=>expect(screen.getByRole('button',{name:'Run paired comparison'})).toBeEnabled())
 expect(fetch).toHaveBeenCalledTimes(1)
})

test('manual review and opt-in save retry reuse receipt without regenerating',async()=>{
 const pair={status:'completed',experiment_id:'unit',original:{id:'root',parent_sample_id:null,text:'Example text',detection:baseline},child:{id:'child',parent_sample_id:'root',text:'Example',detection:baseline},transformation:{operation:'shorten',strength:25,objective:'preserve',edits:[],provider:null},comparison:{evidence_field:'z_score',delta:null,comparable:false,character_delta:-5,token_delta:null,decision_changed:null},warnings:[],receipt:{payload:'unit-receipt',signature:'unit',key_id:'v1'}}
 vi.mocked(fetch).mockResolvedValueOnce({ok:true,json:async()=>pair} as Response).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ok:true,json:async()=>({status:'saved'})} as Response)
 show();await userEvent.type(screen.getByLabelText('Original text'),'Example text')
 await userEvent.click(screen.getByRole('button',{name:'Run paired comparison'}))
 const save=await screen.findByRole('button',{name:'Save experiment'})
 expect(save).toBeDisabled()
 await userEvent.selectOptions(screen.getByLabelText('Meaning preserved'),'yes')
 await userEvent.click(screen.getByLabelText("Save this experiment's signed metadata and evidence."))
 await userEvent.click(save)
 expect(await screen.findByText(/Save failed/)).toBeVisible()
 await userEvent.click(save)
 expect(await screen.findByText('Saved and read back')).toBeVisible()
 expect(save).toBeDisabled()
 expect(fetch).toHaveBeenCalledTimes(3)
 const sent=JSON.parse(vi.mocked(fetch).mock.calls[2][1]!.body as string)
 expect(sent).toMatchObject({payload:'unit-receipt',retain_text:false,original_text:null,child_text:null,manual_review:{meaning:'yes'}})
})
