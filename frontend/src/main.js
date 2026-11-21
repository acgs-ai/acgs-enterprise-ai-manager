import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/main.css'
import { clearLegacyToken } from './auth/oidc'

clearLegacyToken() // drop the pre-OIDC localStorage token

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
