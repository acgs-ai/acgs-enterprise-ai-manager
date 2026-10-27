# ACGS Enterprise Manager - Frontend

Vue.js frontend application for the ACGS Enterprise Manager system.

## Features

- Vue 3 with Composition API
- Vue Router for navigation
- Pinia for state management
- Axios for API communication
- Vite for fast development and building

## Project Structure

```
frontend/
├── src/
│   ├── api/          # API client configuration
│   ├── assets/       # Static assets and styles
│   ├── components/   # Reusable Vue components
│   ├── router/       # Vue Router configuration
│   ├── store/        # Pinia stores
│   ├── views/        # Page components
│   ├── App.vue       # Root component
│   └── main.js       # Application entry point
├── index.html
├── package.json
└── vite.config.js
```

## Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Domain Views

The application includes CRUD interfaces for 6 domains:

1. **Tasks** - Task management with status and priority tracking
2. **IT Assets** - Hardware, software, and license management
3. **Infrastructure** - Server, network, storage, and cloud infrastructure
4. **Projects** - Project lifecycle management
5. **Financial** - Income and expense tracking
6. **Documents** - Document management with categorization

## Authentication

The application uses JWT token-based authentication. Tokens are stored in localStorage and automatically included in API requests.

## API Integration

The frontend connects to the FastAPI backend at `http://localhost:8000`. API endpoints are proxied through Vite during development.

All API calls go through `/api/v1` prefix and include:
- Automatic token injection
- Error handling with 401 redirect
- Request/response interceptors

## Authentication

The app signs users in through an external OIDC identity provider using Authorization Code + PKCE
(`oidc-client-ts`). The backend has no login endpoint: it only verifies the bearer access token
(issuer, audience, signature) on every `/api/v1` route.

1. Copy `.env.example` to `.env.local` and set at least `VITE_OIDC_AUTHORITY` and `VITE_OIDC_CLIENT_ID`.
   Without them the Login page shows "SSO not configured".
2. Register a public **Single-Page Application** client at the IdP: PKCE enabled, no client secret,
   redirect URI `<origin>/callback`, post-logout redirect URI `<origin>/login`.
3. Make the IdP issue access tokens whose audience is the API's configured audience (set
   `VITE_OIDC_AUDIENCE` for IdPs that need an `audience` parameter). The `Authorization` header carries the
   access token, never the ID token.
4. Silent renewal uses refresh tokens (no iframe): allow the refresh-token grant for the client and include
   `offline_access` in `VITE_OIDC_SCOPE` if the IdP requires it.

Tokens live in `sessionStorage` (cleared when the tab closes), never `localStorage`. On a 401 the client
tries one silent renew, then restarts login with the current route as `returnTo` (same-origin paths only).

```bash
npm test   # vitest: returnTo sanitiser + bearer interceptor
```
