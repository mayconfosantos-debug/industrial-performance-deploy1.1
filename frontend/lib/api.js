// Vercel Services: frontend e backend usam o mesmo domínio.
// Fase 1: cache curto em memória no navegador para evitar recalcular a mesma tela ao navegar e voltar.
export const API = ''
const memoryCache = new Map()
const TTL_MS = 120000

export async function getJSON(path, opts = {}) {
  const method = String(opts.method || 'GET').toUpperCase()
  const cacheable = method === 'GET'
  if (cacheable) {
    const hit = memoryCache.get(path)
    if (hit && Date.now() - hit.at < TTL_MS) return hit.data
  }
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15000)
  try {
    const res = await fetch(path, { ...opts, cache: 'no-store', signal: controller.signal })
    if (!res.ok) {
      const body = await res.text()
      throw new Error(`HTTP ${res.status}: ${body || res.statusText}`)
    }
    const data = await res.json()
    if (cacheable) memoryCache.set(path, { at: Date.now(), data })
    return data
  } catch (err) {
    if (err?.name === 'AbortError') throw new Error(`Tempo excedido ao acessar ${path}`)
    throw err
  } finally {
    clearTimeout(timeout)
  }
}

export function clearApiCache(){ memoryCache.clear() }
