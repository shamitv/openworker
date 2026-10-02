# Phase 4 — Headless product flows

## Implementation

Use the existing administrator-provisioned username/password accounts and secure browser sessions. Show the signed-in username and the account's workspace path. Label the account engine **Hosted VM** in machine selectors and inventories.

Use typed VM paths and recent workspaces rather than native folder pickers. Remove server-machine Reveal/Open actions, including skill folders and MCP configuration, and refuse their native endpoints in hosted mode. Provide authenticated browser downloads while retaining inline previews. Project files open through Files; the Artifacts section continues to list session outputs.

Generate public-origin machine-join links. Hosted instructions point external machines directly at the HTTPS controller. Enrollment failures show a retry; expired windows can be renewed. Validate enrollment tokens, signed reconnects, account ownership, and remote workspace requests without a desktop session on the VM.

Scope decision on 2026-10-02: Phase 4 completion covers the password-based hosted experience. The implemented external OAuth URL/callback routing remains covered by backend regressions, but live provider consent and callback acceptance moves to [Phase 5](../phase-05-deployment-and-verification/plan.md). This does not establish third-party OAuth integration acceptance.

## Acceptance

A browser user can sign in with username/password, select a permitted VM workspace, preview and download a file, and enroll an external machine using the generated HTTPS URL. Two independent accounts cannot retrieve one another's artifacts or control one another's machines. Logout and session expiry revoke browser access; the peer account remains usable. Invalid, used, disarmed, and expired enrollment tokens fail.

Nothing invokes a native folder picker or file manager on the VM for these flows. The built SPA passes the explicit HTTPS gate with Chromium and Firefox, real private engines and OpenShell, plus an external CLI joiner. Hermetic GUI tests cover failure and expiry states; backend tests cover token expiry over a real socket and native endpoint refusal. Record commands, results, cleanup, and the deferred OAuth gate in `status.md`.
