const API = `http://${location.hostname}:10046`

export async function req(path, opts = {}) {
  const r = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!r.ok) throw new Error((await r.text()).slice(0, 300))
  return r.json()
}

export const api = {
  base: API,
  staticUrl: (rel) => `${API}/static/output/${rel}`,
  listProjects: () => req('/api/projects'),
  createProject: (body) => req('/api/projects', { method: 'POST', body: JSON.stringify(body) }),
  getProject: (pid) => req(`/api/projects/${pid}`),
  saveScript: (pid, script) => req(`/api/projects/${pid}/script`, { method: 'PUT', body: JSON.stringify(script) }),
  produce: (pid) => req(`/api/projects/${pid}/produce`, { method: 'POST' }),
  regenScript: (pid) => req(`/api/projects/${pid}/regen_script`, { method: 'POST' }),
  regenCharacter: (pid, name) => req(`/api/projects/${pid}/characters/${encodeURIComponent(name)}/regen`, { method: 'POST' }),
  regenShot: (pid, ep, shot, stage) => req(`/api/projects/${pid}/shots/${ep}/${shot}/regen?stage=${stage}`, { method: 'POST' }),
  health: () => req('/api/health/services'),
  wsUrl: (pid) => `ws://${location.hostname}:10046/ws/${pid}`,
}
