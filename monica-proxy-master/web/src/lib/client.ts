import OpenAI from 'openai'
import type { AppConfig } from './settings'

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

function trimBase(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, '')
}

function newClient(config: AppConfig): OpenAI {
  return new OpenAI({
    baseURL: trimBase(config.baseUrl),
    apiKey: config.token || 'no-token',
    dangerouslyAllowBrowser: true,
  })
}

/**
 * Fetch the model list. The proxy's /v1/models returns a minimal
 * `{ data: [{ id }] }` shape, so we read it with a plain fetch rather than
 * relying on the SDK's stricter model typing.
 */
export async function listModels(config: AppConfig): Promise<string[]> {
  const res = await fetch(`${trimBase(config.baseUrl)}/models`, {
    headers: { Authorization: `Bearer ${config.token}` },
  })
  if (!res.ok) {
    throw new Error(`获取模型列表失败 (HTTP ${res.status})`)
  }
  const data = (await res.json()) as { data?: Array<{ id?: string }> }
  return (data.data ?? [])
    .map((m) => m.id)
    .filter((id): id is string => Boolean(id))
    .sort((a, b) => a.localeCompare(b))
}

/**
 * Stream a chat completion. Yields content deltas as they arrive.
 * Pass an AbortSignal to support the Stop button.
 */
export async function* streamChat(
  config: AppConfig,
  model: string,
  messages: ChatMessage[],
  signal: AbortSignal,
): AsyncGenerator<string> {
  const client = newClient(config)
  const stream = await client.chat.completions.create(
    { model, messages, stream: true },
    { signal },
  )
  for await (const chunk of stream) {
    const delta = chunk.choices?.[0]?.delta?.content
    if (delta) {
      yield delta
    }
  }
}
