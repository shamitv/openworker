# Phase 3 — Web gateway and SPA

## Implementation

Add `openworker-web serve` to serve the built Vite SPA and a login page. The gateway terminates browser authentication, then proxies `/v1/*` HTTP and `/ws/*` WebSockets to the signed-in user's loopback engine. Strip client token, actor, cookie, and forwarding headers before proxying; inject the engine launch token and verified actor. Browser requests use same-origin HTTPS/WSS and a session cookie. Match the browser's Origin against one configured public origin on state changes and WebSocket upgrades.

Serve assets with correct cache headers and guard the SPA document behind login. Preserve engine `mode: desktop` with an added hosted-headless capability flag so the existing full UI renders. Add a browser auth boot path, CSRF header insertion, and redirect to login when the web session expires. Keep cloud Auth0 and Tauri flows unchanged. The gateway and engine ports bind only to loopback; the public reverse proxy terminates TLS.

## Acceptance

The SPA loads via HTTPS, starts a session over WebSocket, and survives reload. Engine tokens do not appear in HTML, JavaScript, URLs, or browser storage. Expired sessions, forged actors, cross-origin requests, and unauthorized WebSockets fail.

The required live LLM gate uses the existing OpenAI-compatible provider at the supplied local endpoint, without mocks or fallback. In concurrent Chromium and Firefox sessions, approve uniquely named file writes through the UI and compare account-specific random markers exactly through authenticated downloads and the VM filesystem. Require full OpenShell enforcement, successful tools, an assistant response, turn completion, persistence after reload, cross-account rejection, expiry redirects and continued peer work. Bound each turn to 180 seconds and retain traces, events and logs on failure; missing prerequisites fail the gate.
