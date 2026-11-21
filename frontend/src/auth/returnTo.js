const BASE = 'http://returnto.invalid'
const BLOCKED = ['/login', '/callback']

// Accept only same-origin relative paths ("/foo?x=1#y"). Anything else -> fallback.
export function sanitizeReturnTo(value, fallback = '/') {
  if (typeof value !== 'string' || !value.startsWith('/')) return fallback
  // "//host", "/\host" and control chars are parsed as cross-origin by browsers.
  if (value.startsWith('//') || value.includes('\\')) return fallback
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f]/.test(value)) return fallback

  let url
  try {
    url = new URL(value, BASE)
  } catch {
    return fallback
  }
  if (url.origin !== BASE || BLOCKED.includes(url.pathname)) return fallback
  const result = url.pathname + url.search + url.hash
  // Normalisation ("/..//evil") can yield "//evil"; also reject encoded forms
  // ("/%2F%2Fevil", "/%5c%5cevil") that a router may decode later.
  let decoded
  try {
    decoded = decodeURIComponent(url.pathname)
  } catch {
    return fallback
  }
  for (const p of [url.pathname, decoded]) {
    if (p.startsWith('//') || p.includes('\\')) return fallback
  }
  return result
}
