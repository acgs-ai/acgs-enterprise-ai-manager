import { UserManager, WebStorageStateStore } from 'oidc-client-ts'

const LOGIN_DONE_KEY = 'acgs.auth.loginCompletedAt'

export function getOidcConfig() {
  const env = import.meta.env
  const origin = window.location.origin
  return {
    authority: env.VITE_OIDC_AUTHORITY,
    client_id: env.VITE_OIDC_CLIENT_ID,
    redirect_uri: env.VITE_OIDC_REDIRECT_URI || `${origin}/callback`,
    post_logout_redirect_uri: env.VITE_OIDC_POST_LOGOUT_REDIRECT_URI || `${origin}/login`,
    scope: env.VITE_OIDC_SCOPE || 'openid profile email',
    audience: env.VITE_OIDC_AUDIENCE || ''
  }
}

export function isOidcConfigured() {
  const { authority, client_id } = getOidcConfig()
  return Boolean(authority && client_id)
}

let manager = null

// Created lazily so a missing config surfaces as a Login-view error, not an import crash.
export function getUserManager() {
  if (!isOidcConfigured()) {
    throw new Error('SSO not configured: set VITE_OIDC_AUTHORITY and VITE_OIDC_CLIENT_ID')
  }
  if (!manager) {
    const cfg = getOidcConfig()
    // Tokens AND in-flight login state stay in sessionStorage (oidc-client-ts defaults state to localStorage).
    const store = new WebStorageStateStore({ store: window.sessionStorage })
    manager = new UserManager({
      authority: cfg.authority,
      client_id: cfg.client_id,
      redirect_uri: cfg.redirect_uri,
      post_logout_redirect_uri: cfg.post_logout_redirect_uri,
      response_type: 'code', // Authorization Code + PKCE (S256)
      scope: cfg.scope,
      userStore: store,
      stateStore: store,
      automaticSilentRenew: true, // uses refresh_token grant; no iframe (no silent_redirect_uri)
      extraQueryParams: cfg.audience ? { audience: cfg.audience } : undefined
    })
  }
  return manager
}

// Access token for the API. NOT the id_token: the backend validates the audience.
export async function getAccessToken() {
  if (!isOidcConfigured()) return null
  const user = await getUserManager().getUser()
  return user && !user.expired ? user.access_token : null
}

export async function renewAccessToken() {
  const user = await getUserManager().signinSilent()
  return user ? user.access_token : null
}

// Redirect-loop guard: a 401 right after a completed login means the API rejects our token
// (audience/issuer misconfig); another round-trip through the IdP would not help.
export function markLoginCompleted() {
  try {
    window.sessionStorage.setItem(LOGIN_DONE_KEY, String(Date.now()))
  } catch {
    /* storage unavailable */
  }
}

export function loggedInRecently(windowMs = 30000) {
  try {
    const at = Number(window.sessionStorage.getItem(LOGIN_DONE_KEY))
    return at > 0 && Date.now() - at < windowMs
  } catch {
    return false
  }
}

export function clearLegacyToken() {
  try {
    window.localStorage.removeItem('auth_token')
  } catch {
    /* storage unavailable */
  }
}
