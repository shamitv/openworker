# Phase 3 todo

- [x] Add the loopback-only `openworker-web serve` command, login delivery, SPA serving, and hosted capability flag.
- [x] Add authenticated HTTP and WebSocket proxying with client credential/header stripping and gateway-side token injection.
- [x] Enforce the configured public origin and CSRF token on state-changing browser requests and origin checks on browser WebSockets.
- [x] Add frontend hosted-session startup, CSRF propagation, and redirect to login after session expiry.
- [x] Add gateway tests using separate fake engines for account routing, HTTP/WebSocket proxying, CSRF/origin rejection, and token non-disclosure.
- [x] Add and run tests for expired WebSocket sessions, forwarded-header deployment behavior, SPA asset handling, and remaining proxy edge cases.
- [x] Verify the gateway through a real HTTPS reverse proxy from two independent browsers.
- [x] Verify the supplied real LLM with two fully enforced OpenShell sessions, UI-approved writes, exact artifacts, persistence, isolation, expiry and token non-disclosure.
- [x] Run backend/GUI/build/browser regressions, retain private evidence, and clean up the isolated deployment.
