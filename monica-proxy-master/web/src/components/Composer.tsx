import { useRef } from 'react'
import { ArrowUp, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface ComposerProps {
  onSend: (text: string) => void
  onStop: () => void
  isStreaming: boolean
  disabled?: boolean
  placeholder?: string
}

export function Composer({ onSend, onStop, isStreaming, disabled, placeholder }: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null)

  const resize = () => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  const submit = () => {
    const el = ref.current
    if (!el) return
    const text = el.value
    if (!text.trim() || disabled || isStreaming) return
    onSend(text)
    el.value = ''
    resize()
  }

  return (
    <div
      className={cn(
        'flex items-end gap-2 rounded-2xl border bg-background p-2 shadow-sm transition focus-within:ring-1 focus-within:ring-ring',
        disabled && 'opacity-60',
      )}
    >
      <textarea
        ref={ref}
        rows={1}
        disabled={disabled}
        placeholder={placeholder}
        onInput={resize}
        onKeyDown={(e) => {
          // Enter sends; Shift+Enter inserts a newline. Ignore Enter mid-IME
          // composition so Chinese/Japanese input isn't cut off.
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            submit()
          }
        }}
        className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
      />
      {isStreaming ? (
        <Button
          size="icon"
          variant="secondary"
          onClick={onStop}
          title="停止生成"
          className="h-9 w-9 shrink-0 rounded-xl"
        >
          <Square className="h-4 w-4" />
        </Button>
      ) : (
        <Button
          size="icon"
          onClick={submit}
          disabled={disabled}
          title="发送"
          className="h-9 w-9 shrink-0 rounded-xl"
        >
          <ArrowUp className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}
