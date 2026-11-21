<template>
  <div class="login-container">
    <div class="login-card">
      <h2>ACGS Enterprise Manager</h2>
      <div v-if="error" class="error">{{ error }}</div>
      <p v-if="error" class="subtitle"><router-link to="/login">Back to sign in</router-link></p>
      <p v-else class="subtitle">Completing sign in...</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const authStore = useAuthStore()
const error = ref('')

onMounted(async () => {
  try {
    await authStore.handleCallback(router)
  } catch (e) {
    error.value = e?.message || 'Sign in failed'
  }
})
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
  margin-bottom: 1rem;
}
</style>
