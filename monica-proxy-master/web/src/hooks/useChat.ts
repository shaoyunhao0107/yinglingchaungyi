import { useCallback, useRef, useState } from 'react'
import { listModels, streamChat, type ChatMessage } from '@/lib/client'
import type { AppConfig } from '@/lib/settings'

export interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** true when this assistant message represents an error. */
  error?: boolean
}

let idCounter = 0
function nextId(): string {
  idCounter += 1
  return `m${idCounter}-${Date.now()}`
}

export interface UseChat {
  messages: UiMessage[]
  isStreaming: boolean
  send: (text: string) => void
  stop: () => void
  clear: () => void
}

export function useChat(config: AppConfig, model: string): UseChat {
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  // Keep latest messages available inside the async send without re-creating it.
  const messagesRef = useRef<UiMessage[]>([])
  messagesRef.current = messages

  const appendToLast = useCallback((delta: string) => {
    setMessages((prev) => {
      const next = prev.slice()
      const last = next[next.length - 1]
      if (last && last.role === 'assistant') {
        next[next.length - 1] = { ...last, content: last.content + delta }
      }
      return next
    })
  }, [])

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || isStreaming) return

      const history: ChatMessage[] = messagesRef.current
        .filter((m) => !m.error)
        .map((m) => ({ role: m.role, content: m.content }))
      history.push({ role: 'user', content: trimmed })

      const userMsg: UiMessage = { id: nextId(), role: 'user', content: trimmed }
      const assistantMsg: UiMessage = { id: nextId(), role: 'assistant', content: '' }
      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      ;(async () => {
        try {
          for await (const delta of streamChat(config, model, history, controller.signal)) {
            appendToLast(delta)
          }
        } catch (err) {
          if (controller.signal.aborted) {
            // User pressed Stop: keep whatever streamed so far.
          } else {
            const message = err instanceof Error ? err.message : String(err)
            setMessages((prev) => {
              const next = prev.slice()
              const last = next[next.length - 1]
              if (last && last.role === 'assistant') {
                next[next.length - 1] = {
                  ...last,
                  content: last.content || `请求失败：${message}`,
                  error: true,
                }
              }
              return next
            })
          }
        } finally {
          setIsStreaming(false)
          abortRef.current = null
        }
      })()
    },
    [appendToLast, config, isStreaming, model],
  )

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const clear = useCallback(() => {
    abortRef.current?.abort()
    setMessages([])
  }, [])

  return { messages, isStreaming, send, stop, clear }
}

// Re-export so callers can prefetch models without reaching into lib/client.
export { listModels }
