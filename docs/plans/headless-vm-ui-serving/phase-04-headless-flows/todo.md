# Phase 4 todo

- [x] Gate native folder-picker and server-machine reveal/open controls in hosted browser mode; expose the account workspace path.
- [x] Add authenticated artifact download through the gateway and keep the engine download scoped to the signed-in account.
- [x] Generate browser-facing OAuth URLs and route allowlisted callbacks through the gateway to the account engine for engine-side state validation.
- [x] Generate public-origin machine join links and account-scoped machine WebSocket routes.
- [x] Add backend tests for artifact account scoping, callback route scoping, OAuth redirect generation, and join URL parsing/WebSocket URL construction.
- [ ] Verify workspace selection, artifact download, provider consent and callback, and machine join from a hosted browser and external machine.
- [ ] Add and run end-to-end hosted GUI flow tests, including failure and expired-flow cases.
