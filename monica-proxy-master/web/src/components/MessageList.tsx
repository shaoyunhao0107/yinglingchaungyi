import type { UiMessage } from '@/hooks/useChat'
import { MessageBubble } from './MessageBubble'

export function MessageList({ messages }: { messages: UiMessage[] }) {
  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
    </div>
  )
}
