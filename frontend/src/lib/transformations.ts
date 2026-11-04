import { z } from 'zod'
import { apiBaseUrl } from './api'

export const transformCapabilities=z.object({status:z.string(),message:z.string(),model:z.string().nullable(),max_characters:z.number(),retains_text:z.boolean(),external_provider:z.string(),system_instruction:z.string(),prompt_version:z.string(),operations:z.record(z.string(),z.string()),objectives:z.record(z.string(),z.string()),generation_settings:z.record(z.string(),z.unknown())})
export const transformResult=z.object({transformed_text:z.string().min(1),change_summary:z.string(),operation:z.string(),objective:z.string(),model:z.string(),model_version:z.string().nullable(),prompt_version:z.string(),generation_settings:z.record(z.string(),z.unknown()),source_characters:z.number(),output_characters:z.number(),execution_ms:z.number(),usage:z.object({input_tokens:z.number().nullable(),output_tokens:z.number().nullable(),thinking_tokens:z.number().nullable(),total_tokens:z.number().nullable()}),provenance:z.literal('UNKNOWN'),warnings:z.array(z.string())})
export type TransformResult=z.infer<typeof transformResult>

export async function transformRequest(path:string,token?:string,body?:unknown) {
  const response=await fetch(`${apiBaseUrl()}/api/v1/${path}`,{method:body?'POST':'GET',credentials:'omit',signal:AbortSignal.timeout(125000),
    headers:{Accept:'application/json',...(token?{Authorization:`Bearer ${token}`} :{}),...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined})
  if(!response.ok) {
    if(response.status===401) throw new Error('Your session was not accepted. Sign in again.')
    let message='Transformation unavailable. Check the local API and retry manually.'
    try {
      const parsed=z.object({detail:z.object({code:z.string(),message:z.string().max(500),retryable:z.boolean()})}).parse(await response.json())
      message=parsed.detail.message
    } catch { if(response.status===422) message='Check the input, options and external-processing consent.'; if(response.status===413) message='Input exceeds the allowed request size.' }
    throw new Error(message)
  }
  return response.json()
}
