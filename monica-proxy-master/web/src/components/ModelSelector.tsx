import { useState } from 'react'
import { Check, ChevronDown, Sparkles } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { cn } from '@/lib/utils'

interface ModelSelectorProps {
  models: string[]
  value: string
  onChange: (model: string) => void
  disabled?: boolean
}

export function ModelSelector({ models, value, onChange, disabled }: ModelSelectorProps) {
  const [open, setOpen] = useState(false)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        disabled={disabled}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-accent disabled:pointer-events-none disabled:opacity-50',
        )}
      >
        <Sparkles className="h-4 w-4 text-primary" />
        <span>{value || '选择模型'}</span>
        <ChevronDown className="h-4 w-4 text-muted-foreground" />
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0">
        <Command>
          <CommandInput placeholder="搜索模型…" />
          <CommandList>
            <CommandEmpty>没有匹配的模型</CommandEmpty>
            {models.map((model) => (
              <CommandItem
                key={model}
                value={model}
                onSelect={() => {
                  onChange(model)
                  setOpen(false)
                }}
              >
                <Sparkles className="h-4 w-4 text-primary/70" />
                <span className="flex-1 truncate">{model}</span>
                {value === model && <Check className="h-4 w-4" />}
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
