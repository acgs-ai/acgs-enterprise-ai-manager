import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// Production-only CSP meta: connect-src needs the OIDC authority origin, known only from env at build.
// Skipped in dev because Vite's HMR client needs inline scripts and a websocket.
function cspPlugin() {
  let authority = ''
  return {
    name: 'inject-csp',
    apply: 'build',
    configResolved(config) {
      authority = loadEnv(config.mode, config.envDir || process.cwd(), 'VITE_').VITE_OIDC_AUTHORITY || ''
    },
    transformIndexHtml() {
      let origin = ''
      try {
        if (authority) origin = new URL(authority).origin
      } catch {
        // invalid authority: leave connect-src at 'self'
      }
      const csp = `default-src 'self'; script-src 'self'; connect-src 'self'${origin ? ' ' + origin : ''}; img-src 'self' data:; object-src 'none'; base-uri 'self'`
      return [{ tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content: csp }, injectTo: 'head-prepend' }]
    }
  }
}

export default defineConfig({
  plugins: [vue(), cspPlugin()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
