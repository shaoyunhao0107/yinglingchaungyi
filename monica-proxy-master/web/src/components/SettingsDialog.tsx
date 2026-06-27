import { useEffect, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { AppConfig } from '@/lib/settings'

interface SettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: AppConfig
  onSave: (config: AppConfig) => void
}

export function SettingsDialog({ open, onOpenChange, config, onSave }: SettingsDialogProps) {
  const [baseUrl, setBaseUrl] = useState(config.baseUrl)
  const [token, setToken] = useState(config.token)

  // Re-sync the form whenever the dialog is (re)opened.
  useEffect(() => {
    if (open) {
      setBaseUrl(config.baseUrl)
      setToken(config.token)
    }
  }, [open, config])

  const canSave = baseUrl.trim() !== '' && token.trim() !== ''

  const handleSave = () => {
    if (!canSave) return
    onSave({ baseUrl: baseUrl.trim(), token: token.trim() })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>连接设置</DialogTitle>
          <DialogDescription>填写 monica-proxy 的地址与访问令牌，仅保存在本地浏览器。</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Base URL</label>
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://localhost:8080/v1"
              spellCheck={false}
            />
            <p className="text-xs text-muted-foreground">代理地址，需以 /v1 结尾。</p>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Bearer Token</label>
            <Input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="代理的 BEARER_TOKEN"
              spellCheck={false}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSave()
              }}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSave} disabled={!canSave}>
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
