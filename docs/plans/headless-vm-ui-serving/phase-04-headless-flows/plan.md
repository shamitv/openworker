# Phase 4 — Headless product flows

## Implementation

In hosted-headless mode, use VM paths and recent workspaces rather than trying to open a native folder picker. Remove server-machine Reveal/Open actions and provide authenticated artifact downloads while retaining inline preview. Return connector and MCP OAuth authorization URLs to the caller's browser, then route callbacks through the gateway to the correct engine using short-lived, single-use flow state. Generate public-origin callback and machine-join URLs instead of loopback URLs. Preserve existing desktop and local browser behavior.

## Acceptance

A browser user can select a permitted VM workspace, download an artifact, complete OAuth, and use generated join links without a desktop session on the VM. Nothing tries to open `zenity`, `xdg-open`, or a browser on the VM for these flows.
