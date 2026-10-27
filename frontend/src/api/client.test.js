import { describe, it, expect, vi, beforeAll } from 'vitest'

vi.mock('oidc-client-ts', () => ({
  WebStorageStateStore: class {},
  UserManager: class {
    getUser() {
      return Promise.resolve({ access_token: 'ACCESS', id_token: 'IDTOKEN', expired: false })
    }
  }
}))

let apiClient

beforeAll(async () => {
  vi.stubGlobal('window', {
    location: { origin: 'http://localhost:3000' },
    sessionStorage: {},
    localStorage: {}
  })
  vi.stubEnv('VITE_OIDC_AUTHORITY', 'https://idp.example.com/')
  vi.stubEnv('VITE_OIDC_CLIENT_ID', 'spa')
  apiClient = (await import('./client')).default
})

describe('api client request interceptor', () => {
  it('sets Authorization: Bearer from the UserManager access_token (not id_token)', async () => {
    const handler = apiClient.interceptors.request.handlers[0].fulfilled
    const config = await handler({ headers: {} })
    expect(config.headers.Authorization).toBe('Bearer ACCESS')
  })
})
