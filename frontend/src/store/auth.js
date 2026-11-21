import { defineStore } from 'pinia'
import { getUserManager, markLoginCompleted } from '@/auth/oidc'
import { sanitizeReturnTo } from '@/auth/returnTo'

let initPromise = null

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null // oidc-client-ts User
  }),

  getters: {
    isAuthenticated: (state) => !!state.user && !state.user.expired,
    currentUser: (state) => {
      const p = state.user?.profile
      return p ? { sub: p.sub, email: p.email, name: p.name, role: p.role } : null
    }
  },

  actions: {
    // Idempotent: loads the persisted user once and wires renew/expiry events.
    init() {
      if (!initPromise) {
        initPromise = (async () => {
          let mgr
          try {
            mgr = getUserManager()
          } catch {
            return // not configured; Login view reports it
          }
          mgr.events.addUserLoaded((u) => { this.user = u })
          mgr.events.addUserUnloaded(() => { this.user = null })
          mgr.events.addAccessTokenExpired(() => { this.user = null })
          try {
            let user = await mgr.getUser()
            if (user?.expired && user.refresh_token) {
              user = await mgr.signinSilent().catch(() => null)
            }
            this.user = user && !user.expired ? user : null
          } catch {
            this.user = null
          }
        })()
      }
      return initPromise
    },

    async login(returnTo = '/') {
      await getUserManager().signinRedirect({ state: { returnTo: sanitizeReturnTo(returnTo) } })
    },

    // Completes the redirect, then navigates to the sanitised returnTo.
    async handleCallback(router) {
      const user = await getUserManager().signinRedirectCallback()
      this.user = user
      markLoginCompleted()
      const target = sanitizeReturnTo(user.state?.returnTo)
      await router.replace(target)
      return target
    },

    async clearSession() {
      this.user = null
      try {
        await getUserManager().removeUser()
      } catch {
        /* not configured */
      }
    },

    async logout() {
      try {
        await getUserManager().signoutRedirect()
      } catch {
        // IdP without end_session_endpoint: fall back to a local sign-out.
        await this.clearSession()
        window.location.assign('/login')
      }
    }
  }
})
