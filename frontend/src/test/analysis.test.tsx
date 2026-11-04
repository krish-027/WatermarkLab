// UI tests mock transport/auth only. Scientific acceptance is tested with real
// MarkLLM in backend tests and real hosted-auth + local-detector browser tests.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, test, vi } from 'vitest'
import Analysis, { Evidence } from '../pages/Analysis'
import { resultSchema } from '../lib/analysis'

vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ session: { access_token: 'ui-unit-only', user: { id: 'unit' } } }) }))
const caps = { detectors: [{ method: 'KGW', status: 'ready', message: 'Unit transport ready' }], max_characters: 20000, max_tokens: 4096, retains_text: false }
const inconclusive = { method:'KGW',profile_id:null,verdict:'INCONCLUSIVE',provenance:'UNKNOWN',provenance_source:'user declaration; not independently verified',compatibility_basis:'unknown', character_count:12,token_count:null,scored_token_count:null,green_token_count:null,repeated_pair_count:null,raw_score:null,z_score:null,p_value:null,threshold:null,decision_rule:null,native:null,execution_ms:1,warnings:['Unknown compatibility cannot be scored.'] }
const synthidResult={...inconclusive,method:'SYNTHID',profile_id:'synthid-threefry-gpt2-cpu-v1',verdict:'DETECTED',
  token_count:200,scored_token_count:195,p_value:1.907783774589299e-54,threshold:.01,decision_rule:'p <= 0.01',
  native:{p_value:1.907783774589299e-54},g_value_ones:3516,g_value_trials:5850,masked_position_count:1,
  repeated_context_count:1,eos_masked_position_count:0,compatibility_status:'declared'}
beforeEach(() => {
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async (url: string) => ({ok:true,json:async () => url.endsWith('capabilities') ? caps : url.endsWith('samples') ? [] : inconclusive})))
})
function show() {
  return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}})}><MemoryRouter><Analysis /></MemoryRouter></QueryClientProvider>)
}
test('empty input validation prevents analysis submission', async () => {
  show()
  const run = await screen.findByRole('button',{name:'Analyze KGW'})
  await waitFor(() => expect(run).toBeEnabled())
  await userEvent.click(run)
  expect(screen.getByRole('alert')).toHaveTextContent('Enter text')
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/analyze'))).toBe(false)
})
test('unknown profile remains explicitly inconclusive, never a fabricated score', async () => {
  show()
  await userEvent.type(screen.getByLabelText('Text to analyze'),'Example text')
  await userEvent.click(await screen.findByRole('button',{name:'Analyze KGW'}))
  expect(await screen.findByRole('heading',{name:'INCONCLUSIVE'})).toBeInTheDocument()
  expect(screen.getByText('Unknown compatibility cannot be scored.')).toBeInTheDocument()
  expect(screen.getByText('Not available')).toBeInTheDocument()
})
test('availability errors have a retry and disable submission', async () => {
  vi.mocked(fetch).mockRejectedValue(new Error('offline'))
  show()
  expect(await screen.findByRole('button',{name:'Retry availability'})).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Analyze KGW'})).toBeDisabled()
})
test('missing research setup is actionable and cannot pretend to run', async () => {
  vi.mocked(fetch).mockImplementation(async (url) => ({ok:true,json:async () => String(url).endsWith('capabilities') ? {...caps,detectors:[{method:'KGW',status:'setup required',message:'Install optional requirements and tokenizer.'}]} : []}) as Response)
  show()
  expect(await screen.findByText(/Install optional requirements/)).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Analyze KGW'})).toBeDisabled()
})
test('typing resets compatibility and provenance; clear removes input', async () => {
  show()
  await userEvent.selectOptions(screen.getByLabelText('KGW profile'),'kgw-gpt2-cpu-v1')
  const checkbox = screen.getByRole('checkbox')
  await userEvent.click(checkbox)
  await userEvent.selectOptions(screen.getByLabelText('Provenance declaration'),'KNOWN_WATERMARKED')
  await userEvent.type(screen.getByLabelText('Text to analyze'),'Changed text')
  expect(checkbox).not.toBeChecked()
  expect(screen.getByLabelText('Provenance declaration')).toHaveValue('UNKNOWN')
  await userEvent.click(screen.getByRole('button',{name:'Clear text'}))
  expect(screen.getByLabelText('Text to analyze')).toHaveValue('')
})
test('upload rejects unsupported extensions and oversize files', async () => {
  show()
  const user=userEvent.setup({applyAccept:false})
  const input=screen.getByLabelText(/Upload UTF-8/)
  await user.upload(input,new File(['text'],'sample.exe'))
  expect(screen.getByRole('alert')).toHaveTextContent('Choose a UTF-8')
  await user.upload(input,new File(['x'.repeat(80001)],'sample.txt'))
  expect(screen.getByRole('alert')).toHaveTextContent('80 KB')
})
test('native result rendering never converts evidence to an authorship percentage', () => {
  // Recorded native result from genuine pilot-1-wm; UI rendering only.
  const result=resultSchema.parse({...inconclusive,profile_id:'kgw-gpt2-cpu-v1',verdict:'DETECTED',z_score:9.2863437856092,raw_score:9.2863437856092,token_count:200,scored_token_count:199,threshold:4,decision_rule:'z > 4.0',native:{score:9.2863437856092,is_watermarked:true}})
  render(<Evidence result={result} />)
  expect(screen.getByText('9.2863')).toBeInTheDocument()
  expect(screen.getByText('z > 4.0')).toBeInTheDocument()
  expect(screen.getByText(/not an AI-authorship probability/)).toBeInTheDocument()
})
test('request failure produces retryable error, not evidence', async () => {
  const fetchMock=vi.mocked(fetch)
  fetchMock.mockImplementation(async url => {
    if (String(url).endsWith('/analyze')) return {ok:false,status:429} as Response
    return {ok:true,json:async () => String(url).endsWith('capabilities') ? caps : []} as Response
  })
  show()
  await userEvent.type(screen.getByLabelText('Text to analyze'),'Example text')
  await userEvent.click(screen.getByRole('button',{name:'Analyze KGW'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Detector busy')
  expect(screen.queryByRole('heading',{name:'DETECTED'})).not.toBeInTheDocument()
})

test('SynthID displays native p-value and masks without KGW evidence', () => {
  render(<Evidence result={resultSchema.parse(synthidResult)} />)
  expect(screen.getByText('1.9078e-54')).toBeInTheDocument()
  expect(screen.getByText('3516 / 5850')).toBeInTheDocument()
  expect(screen.getByText('p <= 0.01')).toBeInTheDocument()
  expect(screen.queryByText('Native z-score')).not.toBeInTheDocument()
  expect(screen.queryByText('Green tokens')).not.toBeInTheDocument()
  expect(screen.getByText(/not an AI-authorship probability or a population/)).toBeInTheDocument()
})

test('statistical response contracts reject mixed evidence', () => {
  expect(resultSchema.safeParse({...synthidResult,z_score:4}).success).toBe(false)
  expect(resultSchema.safeParse({...inconclusive,p_value:.1}).success).toBe(false)
})

test('method switching resets profile and declarations and calls the selected detector', async () => {
  vi.mocked(fetch).mockImplementation(async (url,options) => {
    const path=String(url)
    return {ok:true,json:async () => path.endsWith('capabilities') ? {...caps,detectors:[...caps.detectors,{method:'SYNTHID',status:'ready',message:'Research core ready',max_tokens:1024}]} : path.endsWith('samples') ? [] : JSON.parse(String(options?.body)).method==='SYNTHID' ? synthidResult : inconclusive} as Response
  })
  show()
  await userEvent.selectOptions(screen.getByLabelText('KGW profile'),'kgw-gpt2-cpu-v1')
  await userEvent.click(screen.getByRole('checkbox'))
  await userEvent.selectOptions(screen.getByLabelText('Detector method'),'SYNTHID')
  expect(screen.getByLabelText('SynthID profile')).toHaveValue('')
  expect(screen.getByRole('checkbox')).not.toBeChecked()
  await userEvent.type(screen.getByLabelText('Text to analyze'),'Unit transport test input')
  await userEvent.click(screen.getByRole('button',{name:'Analyze SynthID'}))
  expect(await screen.findByText('1.9078e-54')).toBeInTheDocument()
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/synthid/samples'))).toBe(true)
  await userEvent.selectOptions(screen.getByLabelText('Detector method'),'KGW')
  expect(screen.queryByText('1.9078e-54')).not.toBeInTheDocument()
  expect(screen.getByLabelText('KGW profile')).toHaveValue('')
})

test('unsupported SynthID profile status and native-short evidence are explicit', () => {
  render(<Evidence result={resultSchema.parse({...synthidResult,verdict:'INCONCLUSIVE',compatibility_status:'unsupported',p_value:null,native:null,warnings:['Unsupported profile.']})} />)
  expect(screen.getByText(/unsupported ·/)).toBeInTheDocument()
  expect(screen.getByRole('heading',{name:'INCONCLUSIVE'})).toBeInTheDocument()
})

test('missing SynthID setup disables its analysis while KGW remains usable', async () => {
  vi.mocked(fetch).mockImplementation(async url => ({ok:true,json:async () => String(url).endsWith('capabilities') ? {...caps,detectors:[...caps.detectors,{method:'SYNTHID',status:'setup required',message:'Install pinned SciPy and core.'}]} : []}) as Response)
  show()
  await screen.findByText(/Unit transport ready/)
  await userEvent.selectOptions(screen.getByLabelText('Detector method'),'SYNTHID')
  expect(screen.getByText(/Install pinned SciPy/)).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Analyze SynthID'})).toBeDisabled()
  await userEvent.selectOptions(screen.getByLabelText('Detector method'),'KGW')
  expect(screen.getByRole('button',{name:'Analyze KGW'})).toBeEnabled()
})
