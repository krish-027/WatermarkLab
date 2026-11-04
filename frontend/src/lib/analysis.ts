import { z } from 'zod'
import { apiBaseUrl } from './api'

const detector = z.object({ method: z.string(), status: z.string(), message: z.string(), profile_id: z.string().optional(), model: z.string().optional(), tokenizer_revision: z.string().optional(), reference_revision: z.string().optional(), threshold: z.number().optional(), decision_rule: z.string().optional(), max_tokens: z.number().optional() })
export const capabilitiesSchema = z.object({ detectors: z.array(detector), max_characters: z.number(), max_tokens: z.number(), retains_text: z.boolean() })
export type Capabilities = z.infer<typeof capabilitiesSchema>
export const resultSchema = z.object({
  method: z.enum(['KGW','SYNTHID']), profile_id: z.string().nullable(), verdict: z.enum(['DETECTED', 'NOT DETECTED', 'INCONCLUSIVE', 'UNAVAILABLE']),
  provenance: z.string(), provenance_source: z.string(), compatibility_basis: z.string(), character_count: z.number(),
  token_count: z.number().nullable(), scored_token_count: z.number().nullable(), green_token_count: z.number().nullable(),
  compatibility_status: z.enum(['unknown','declared','unsupported']).default('unknown'),
  repeated_pair_count: z.number().nullable(), raw_score: z.number().nullable(), z_score: z.number().nullable(), p_value: z.number().min(0).max(1).nullable(),
  g_value_ones: z.number().nullable().default(null), g_value_trials: z.number().nullable().default(null),
  masked_position_count: z.number().nullable().default(null), repeated_context_count: z.number().nullable().default(null), eos_masked_position_count: z.number().nullable().default(null),
  threshold: z.number().nullable(), decision_rule: z.string().nullable(), execution_ms: z.number(), warnings: z.array(z.string()),
  native: z.union([z.object({ score: z.number(), is_watermarked: z.boolean() }).strict(),z.object({p_value:z.number().min(0).max(1)}).strict()]).nullable(),
}).superRefine((result,ctx) => {
  if ((result.method==='KGW' && result.p_value!==null) || (result.method==='SYNTHID' && (result.z_score!==null || result.raw_score!==null || result.green_token_count!==null))) {
    ctx.addIssue({code:'custom',message:'Incompatible statistical evidence'})
  }
})
export type AnalysisResult = z.infer<typeof resultSchema>
export const samplesSchema = z.array(z.object({ id: z.string(), text: z.string(), provenance: z.enum(['KNOWN_WATERMARKED','KNOWN_UNWATERMARKED']), profile_id: z.string(), label_source: z.string() }))
export type Sample = z.infer<typeof samplesSchema>[number]

export async function analysisRequest(path: string, token?: string, body?: unknown) {
  const response = await fetch(`${apiBaseUrl()}/api/v1/${path}`, {
    method: body ? 'POST' : 'GET', credentials: 'omit', signal: AbortSignal.timeout(60000),
    headers: { Accept: 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) throw new Error(response.status === 401 ? 'Your session was not accepted. Sign in again.' : response.status === 429 ? 'Detector busy. Please retry shortly.' : response.status === 413 ? 'Input exceeds the configured size limit.' : response.status === 422 ? 'Invalid input. Check the text and selected configuration.' : 'Analysis service unavailable. Check the local API and retry.')
  return response.json()
}
