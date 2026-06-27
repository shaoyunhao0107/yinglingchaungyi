import { useEffect, useState } from 'react'
import { Settings } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ModelSelector } from '@/components/ModelSelector'
import { SettingsDialog } from '@/components/SettingsDialog'
import { ChatView } from '@/components/ChatView'
import { listModels } from '@/lib/client'
import {
  isConfigured,
  loadConfig,
  loadModel,
  saveConfig,
  saveModel,
  type AppConfig,
} from '@/lib/settings'

export default function App() {
  const [config, setConfig] = useState<AppConfig>(() => loadConfig())
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState<string>(() => loadModel())
  const [settingsOpen, setSettingsOpen] = useState<boolean>(() => !isConfigured(loadConfig()))
  const [modelError, setModelError] = useState<string>('')

  // Refresh the model list whenever the connection settings change.
  useEffect(() => {
    if (!isConfigured(config)) return
    let cancelled = false
    listModels(config)
      .then((list) => {
        if (cancelled) return
        setModels(list)
        setModelError('')
        setModel((cur) => (cur && list.includes(cur) ? cur : (list[0] ?? cur)))
      })
      .catch((err) => {
        if (cancelled) return
        setModels([])
        setModelError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [config])

  useEffect(() => {
    if (model) saveModel(model)
  }, [model])

  const handleSave = (next: AppConfig) => {
    setConfig(next)
    saveConfig(next)
    setSettingsOpen(false)
  }

  const ready = isConfigured(config)

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b px-3 py-2 sm:px-4">
        <div className="flex items-center gap-1.5">
          <span className="px-1 text-sm font-semibold sm:text-base">Monica Chat</span>
          <ModelSelector
            models={models}
            value={model}
            onChange={setModel}
            disabled={!ready || models.length === 0}
          />
        </div>
        <Button variant="ghost" size="icon" onClick={() => setSettingsOpen(true)} title="设置">
          <Settings className="h-5 w-5" />
        </Button>
      </header>

      {modelError && (
        <div className="bg-destructive/10 px-4 py-1.5 text-center text-xs text-destructive">
          无法加载模型列表：{modelError}
        </div>
      )}

      <main className="min-h-0 flex-1">
        <ChatView config={config} model={model} />
      </main>

      <SettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        config={config}
        onSave={handleSave}
      />
    </div>
  )
}
