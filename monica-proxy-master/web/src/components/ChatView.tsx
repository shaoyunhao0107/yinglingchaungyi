import { useEffect, useRef } from 'react'
import { useChat } from '@/hooks/useChat'
import { isConfigured, type AppConfig } from '@/lib/settings'
import { MessageList } from './MessageList'
import { Composer } from './Composer'

interface ChatViewProps {
  config: AppConfig
  model: string
}

function EmptyState() {
  return (
    <div className="flex h-full items-center justify-center">
      <h1 className="px-4 text-center text-2xl font-semibold text-foreground/80 sm:text-3xl">
        今天能帮你做点什么？
      </h1>
    </div>
  )
}

export function ChatView({ config, model }: ChatViewProps) {
  const { messages, isStreaming, send, stop } = useChat(config, model)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to the newest content as it streams.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  const ready = isConfigured(config) && Boolean(model)

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 ? <EmptyState /> : <MessageList messages={messages} />}
      </div>
      <div className="border-t bg-background">
        <div className="mx-auto w-full max-w-3xl px-4 py-3">
          <Composer
            onSend={send}
            onStop={stop}
            isStreaming={isStreaming}
            disabled={!ready}
            placeholder={ready ? '给 Monica 发送消息…' : '请先点击右上角设置，填写地址和令牌'}
          />
          <p className="mt-1.5 text-center text-xs text-muted-foreground">
            内容由 Monica 通过代理生成，仅供参考。
          </p>
        </div>
      </div>
    </div>
  )
}
