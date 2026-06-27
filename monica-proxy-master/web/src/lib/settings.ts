// Persisted connection settings + selected model (localStorage).

export interface AppConfig {
  /** Base URL of the monica-proxy, including the /v1 suffix. */
  baseUrl: string
  /** Bearer token configured on the proxy (BEARER_TOKEN). */
  token: string
}

const CONFIG_KEY = 'monica-ui-settings'
const MODEL_KEY = 'monica-ui-model'

export const DEFAULT_CONFIG: AppConfig = {
  baseUrl: 'http://localhost:8080/v1',
  token: '',
}

export function loadConfig(): AppConfig {
  try {
    const raw = localStorage.getItem(CONFIG_KEY)
    if (!raw) return { ...DEFAULT_CONFIG }
    const parsed = JSON.parse(raw) as Partial<AppConfig>
    return {
      baseUrl: parsed.baseUrl?.trim() || DEFAULT_CONFIG.baseUrl,
      token: parsed.token?.trim() || '',
    }
  } catch {
    return { ...DEFAULT_CONFIG }
  }
}

export function saveConfig(config: AppConfig): void {
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config))
}

export function isConfigured(config: AppConfig): boolean {
  return Boolean(config.baseUrl.trim() && config.token.trim())
}

export function loadModel(): string {
  return localStorage.getItem(MODEL_KEY) || ''
}

export function saveModel(model: string): void {
  localStorage.setItem(MODEL_KEY, model)
}
