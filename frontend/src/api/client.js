import axios from 'axios'
import { getAccessToken, renewAccessToken, loggedInRecently } from '@/auth/oidc'
import { useAuthStore } from '@/store/auth'

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Attach the OIDC access token (not the id_token: the API checks the audience).
apiClient.interceptors.request.use(
  async (config) => {
    const token = await getAccessToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

let renewing = null
let reloginStarted = false

async function reloginOnce() {
  const auth = useAuthStore()
  await auth.clearSession()
  const { pathname, search, hash } = window.location
  // Loop guards: already on an auth page, already redirecting, or the API rejected a token we just obtained.
  if (['/login', '/callback'].includes(pathname) || reloginStarted || loggedInRecently()) return
  reloginStarted = true
  try {
    await auth.login(pathname + search + hash)
  } catch {
    reloginStarted = false
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config
    if (error.response?.status !== 401 || !config) return Promise.reject(error)

    if (!config._retried) {
      config._retried = true
      try {
        renewing ??= renewAccessToken().finally(() => { renewing = null })
        if (await renewing) return apiClient(config) // request interceptor re-reads the fresh token
      } catch {
        /* fall through to re-login */
      }
    }
    await reloginOnce()
    return Promise.reject(error)
  }
)

export default apiClient
