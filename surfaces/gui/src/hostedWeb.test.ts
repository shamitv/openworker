import { afterEach, beforeEach, expect, it, vi } from "vitest";

const origin = "https://worker.example.test";
const valid = { user: "alice", csrf: "alice-csrf", workspace_root: "/alice/workspace" };
const reply = (status = 200, body = valid) => ({ status, ok: status < 400, json: async () => body } as Response);
let replace: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.resetModules();
  replace = vi.fn();
  vi.stubGlobal("__COWORKER_WEB__", true);
  vi.stubGlobal("location", { origin, href: origin + "/", protocol: "https:", host: "worker.example.test", replace });
  vi.stubGlobal("fetch", vi.fn(async () => reply()));
});
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it("boots hosted auth and signs out using the in-memory CSRF token", async () => {
  const auth = await import("./hostedWeb");
  await auth.initHostedWeb();
  expect(auth.webUsername()).toBe("alice");
  expect(auth.webWorkspaceRoot()).toBe("/alice/workspace");
  await auth.webSignOut();
  expect(fetch).toHaveBeenLastCalledWith("/web/auth/logout", expect.objectContaining({ headers: { "X-CSRF-Token": "alice-csrf" }, credentials: "same-origin" }));
  expect(replace).toHaveBeenCalledWith("/web/login");
  expect(auth.webCsrfToken()).toBe("");
});

it("deduplicates validation and redirects expired sessions only once", async () => {
  const auth = await import("./hostedWeb");
  let finish!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(resolve => { finish = resolve; })));
  const one = auth.revalidateHostedWeb();
  const two = auth.revalidateHostedWeb();
  expect(one).toBe(two);
  finish(reply(401));
  expect(await one).toBe(false);
  expect(await auth.revalidateHostedWeb()).toBe(false);
  expect(fetch).toHaveBeenCalledOnce();
  expect(replace).toHaveBeenCalledOnce();
});

it("redirects required password changes and tolerates transient failures", async () => {
  const auth = await import("./hostedWeb");
  vi.stubGlobal("fetch", vi.fn(async () => reply(503)));
  expect(await auth.revalidateHostedWeb()).toBe(true);
  vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
  expect(await auth.revalidateHostedWeb()).toBe(true);
  expect(replace).not.toHaveBeenCalled();
  vi.stubGlobal("fetch", vi.fn(async () => reply(200, { ...valid, must_change: true } as any)));
  expect(await auth.revalidateHostedWeb()).toBe(false);
  expect(replace).toHaveBeenCalledWith("/web/change-password");
});

it("gates startup on session expiry or mandatory password changes", async () => {
  const auth = await import("./hostedWeb");
  vi.stubGlobal("fetch", vi.fn(async () => reply(401)));
  void auth.initHostedWeb();
  await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/web/login"));
});

class Socket {
  static CONNECTING = 0;
  static OPEN = 1;
  readyState = 0;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onopen: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  static instances: Socket[] = [];
  constructor(public url: string, public protocols?: string[]) { Socket.instances.push(this); }
}

it("uses same-origin endpoints, suppresses desktop tokens, and propagates CSRF", async () => {
  vi.stubGlobal("__COWORKER_API_TOKEN__", "never-disclose");
  vi.stubGlobal("__COWORKER_HTTP__", "http://wrong.example");
  vi.stubGlobal("__COWORKER_WS__", "ws://wrong.example");
  vi.stubGlobal("WebSocket", Socket);
  const auth = await import("./hostedWeb");
  await auth.initHostedWeb();
  const api = await import("./api");
  expect(api.httpBase()).toBe(origin);
  await api.connectManaged("github");
  const [url, init] = vi.mocked(fetch).mock.calls.slice(-1)[0]!;
  expect(String(url).startsWith(origin)).toBe(true);
  expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("alice-csrf");
  expect(new Headers(init?.headers).has("X-OpenWorker-Token")).toBe(false);
  const session = new api.Session("s1", "/alice/workspace", "code", { onEvent: vi.fn() });
  expect(Socket.instances.slice(-1)[0]?.url).toMatch(/^wss:\/\/worker.example.test\//);
  expect(Socket.instances.slice(-1)[0]?.protocols).toBeUndefined();
  session.close();
});

it("checks hosted account auth for machine 401 without signing out valid accounts", async () => {
  const api = await import("./api");
  vi.stubGlobal("fetch", vi.fn(async url => String(url).endsWith("/web/auth/session") ? reply() : reply(401)));
  await api.getHealth();
  await api.getMachineSettings("remote");
  await api.getCloudStatus();
  expect(replace).not.toHaveBeenCalled();
  vi.stubGlobal("fetch", vi.fn(async () => reply(401)));
  await api.getHealth();
  expect(replace).toHaveBeenCalledWith("/web/login");
});

it("gates startup on mandatory password changes", async () => {
  const auth = await import("./hostedWeb");
  vi.stubGlobal("fetch", vi.fn(async () => reply(200, { ...valid, must_change: true } as any)));
  void auth.initHostedWeb();
  await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/web/change-password"));
});

it("stops session and event socket retries when hosted auth expires", async () => {
  vi.useFakeTimers();
  Socket.instances = [];
  vi.stubGlobal("WebSocket", Socket);
  vi.stubGlobal("fetch", vi.fn(async () => reply(401)));
  const api = await import("./api");
  const session = new api.Session("s1", "/alice/workspace", "code", { onEvent: vi.fn() });
  const stop = api.connectEvents(vi.fn());
  for (const socket of Socket.instances) socket.onclose?.({ code: 4401 });
  await vi.advanceTimersByTimeAsync(20000);
  expect(Socket.instances).toHaveLength(2);
  expect(replace).toHaveBeenCalledOnce();
  session.close(); stop();
});

it("reconnects sockets on transient failures and cancels retries on disposal", async () => {
  vi.useFakeTimers();
  Socket.instances = [];
  vi.stubGlobal("WebSocket", Socket);
  vi.stubGlobal("fetch", vi.fn(async () => reply(503)));
  const api = await import("./api");
  const session = new api.Session("s1", "/alice/workspace", "code", { onEvent: vi.fn() });
  const stop = api.connectEvents(vi.fn());
  for (const socket of [...Socket.instances]) socket.onclose?.({ code: 1006 });
  await vi.advanceTimersByTimeAsync(5001);
  expect(Socket.instances).toHaveLength(4);
  expect(replace).not.toHaveBeenCalled();
  session.close(); stop();
  await vi.advanceTimersByTimeAsync(30000);
  expect(Socket.instances).toHaveLength(4);
});
