<template>
  <div class="login-container">
    <div class="login-card">
      <h2>ACGS Enterprise Manager</h2>
      <p class="subtitle">Sign in to continue</p>

      <div v-if="error" class="error">{{ error }}</div>

      <button
        type="button"
        class="btn btn-primary btn-block"
        :disabled="loading || !configured"
        @click="handleLogin"
      >
        {{ loading ? 'Redirecting...' : 'Sign in with SSO' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { isOidcConfigured } from '@/auth/oidc'
import { sanitizeReturnTo } from '@/auth/returnTo'

const route = useRoute()
const authStore = useAuthStore()

const configured = isOidcConfigured()
const error = ref(
  configured ? '' : 'SSO not configured: set VITE_OIDC_AUTHORITY and VITE_OIDC_CLIENT_ID.'
)
const loading = ref(false)

const handleLogin = async () => {
  error.value = ''
  loading.value = true
  try {
    await authStore.login(sanitizeReturnTo(route.query.returnTo))
  } catch (e) {
    loading.value = false
    error.value = e?.message || 'Could not start sign in'
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  background: white;
  padding: 2rem;
  border-radius: 8px;
  box-shadow: 0 10px 40px rgba(0,0,0,0.2);
  width: 100%;
  max-width: 400px;
}

.login-card h2 {
  text-align: center;
  color: #2c3e50;
  margin-bottom: 0.5rem;
}

.subtitle {
  text-align: center;
  color: #7f8c8d;
  margin-bottom: 2rem;
}

.btn-block {
  width: 100%;
  margin-top: 1rem;
}
</style>
