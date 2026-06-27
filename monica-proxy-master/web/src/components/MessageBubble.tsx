import { splitThink } from '@/lib/think'
import type { UiMessage } from '@/hooks/useChat'
import { Markdown } from './Markdown'

function ThinkBlock({ content }: { content: string }) {
  return (
    <details className="rounded-lg border bg-muted/40 px-3 py-2" open>
      <summary className="cursor-pointer select-none text-xs font-medium text-muted-foreground">
        思考过程
      </summary>
      <div className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{content}</div>
    </details>
  )
}

export function MessageBubble({ message }: { message: UiMessage }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-primary px-4 py-2.5 text-[15px] text-primary-foreground">
          {message.content}
        </div>
      </div>
    )
  }

  if (message.error) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[85%] rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-2.5 text-sm text-destructive">
          {message.content}
        </div>
      </div>
    )
  }

  // Empty assistant content = response is still being requested.
  if (message.content === '') {
    return (
      <div className="flex justify-start">
        <div className="flex items-center gap-1 px-1 py-3 text-muted-foreground">
          <span className="h-2 w-2 animate-pulse rounded-full bg-current" />
          <span className="h-2 w-2 animate-pulse rounded-full bg-current [animation-delay:150ms]" />
          <span className="h-2 w-2 animate-pulse rounded-full bg-current [animation-delay:300ms]" />
        </div>
      </div>
    )
  }

  const segments = splitThink(message.content)
  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[85%] space-y-2">
        {segments.map((seg, i) =>
          seg.type === 'think' ? (
            <ThinkBlock key={i} content={seg.content} />
          ) : (
            <Markdown key={i} content={seg.content} />
          ),
        )}
      </div>
    </div>
  )
}
