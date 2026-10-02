# Phase 4 todo

- [x] Gate native folder-picker and server-machine reveal/open controls in hosted browser mode; expose the account workspace path.
- [x] Add authenticated artifact download through the gateway and keep the engine download scoped to the signed-in account.
- [x] Generate browser-facing OAuth URLs and route allowlisted callbacks through the gateway to the account engine for engine-side state validation.
- [x] Generate public-origin machine join links and account-scoped machine WebSocket routes.
- [x] Add backend tests for artifact account scoping, callback route scoping, OAuth redirect generation, and join URL parsing/WebSocket URL construction.
- [x] Agree password-based Phase 4 acceptance and move live external OAuth consent/callback verification to Phase 5.
- [x] Show the password-session username and Hosted VM labels, remove desktop tunnel instructions from hosted enrollment, and provide enrollment failure/retry feedback.
- [x] Gate skill-folder reveal in hosted UI and refuse native skill/MCP reveal endpoints server-side.
- [x] Verify password sessions, typed/recent workspace selection, UI preview/downloads, and machine join/reconnect from hosted browsers and an external machine.
- [x] Add and run hosted GUI flow tests, including failure/expiry, account boundaries and invalid/used/disarmed tokens; record backend token-expiry and native-control regressions.
- [x] Retain private evidence and clean up the disposable deployment and external joiner state.
