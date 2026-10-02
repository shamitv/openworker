import { expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";

export type Account = { username: string; password: string; home: string; id: string };
export type Manifest = { origin: string; mode: string; model: string; llm_base_url: string; root: string; source: string; accounts: Account[]; engine_tokens: string[] };
export type Event = { type: string; data?: Record<string, any> };
const quote = (value: string) => "'" + value.replace(/'/g, "'\\''") + "'";

export function control(manifest: Manifest, request: Record<string, string>) {
  const python = process.env.HOSTED_TEST_PYTHON;
  if (!python) throw new Error("HOSTED_TEST_PYTHON must name the fixture host's Python interpreter");
  const args = [manifest.source + "/scripts/hosted_browser_fixture.py", "control", "--root", manifest.root,
    "--request", Buffer.from(JSON.stringify(request)).toString("base64")];
  const runner = process.env.HOSTED_TEST_SSH_RUNNER;
  const stdout = runner
    ? execFileSync(runner, [[python, ...args].map(quote).join(" ")], { encoding: "utf8", timeout: 30_000 })
    : execFileSync(python, args, { encoding: "utf8", timeout: 30_000 });
  return JSON.parse(stdout);
}

export async function newSession(page: Page) {
  const topbar = page.getByTestId("topbar-cluster").getByRole("button", { name: "New session", exact: true });
  if (await topbar.isVisible()) await topbar.click();
  else await page.getByRole("button", { name: "New session", exact: true }).first().click();
}

export async function login(page: Page, manifest: Manifest, account: Account) {
  await page.goto(manifest.origin + "/web/login");
  await page.getByLabel("Username").fill(account.username);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(url => url.origin === manifest.origin && url.pathname === "/");
  await expect(page.getByRole("button", { name: "New session", exact: true })).toBeVisible();
  const session = await (await page.request.get(manifest.origin + "/web/auth/session")).json();
  expect(session.user).toBe(account.username);
  const capabilities = await (await page.request.get(manifest.origin + "/v1/capabilities")).json();
  expect(capabilities).toMatchObject({ mode: "desktop", headless_web: true });
  const headers = { Origin: manifest.origin, "X-CSRF-Token": session.csrf };
  for (const [route, data] of [
    ["/v1/providers", { name: "openai", fields: { api_key: "local-acceptance", base_url: manifest.llm_base_url } }],
    ["/v1/settings/models/add", { model: manifest.model }],
    ["/v1/settings/default-model", { model: manifest.model }],
    ["/v1/settings/onboarded", { value: true }],
    ["/v1/settings/scratch-base", { path: account.home + "/workspace/sessions" }],
  ] as const) {
    const response = await page.request.post(manifest.origin + route, { headers, data });
    expect(response.ok(), route).toBe(true);
    expect((await response.json()).ok, route).not.toBe(false);
  }
  await page.reload();
  await expect(page.getByPlaceholder(/Ask the coworker/)).toBeVisible();
  const cookies = await page.context().cookies();
  const cookie = cookies.find(item => item.name === "__Host-openworker-session")!;
  expect(cookie).toMatchObject({ secure: true, httpOnly: true, sameSite: "Strict", path: "/" });
}

export async function work(page: Page, manifest: Manifest, account: Account, events: Event[], options: { startNewSession?: boolean; workspace?: string } = {}) {
  if (options.startNewSession !== false) await newSession(page);
  const start = events.length;
  const nonce = randomUUID().replaceAll("-", "");
  const filename = `hosted-${account.username}-${nonce}.txt`;
  const prompt = `Create a new file named "${filename}" in this session's workspace. Its complete contents must be exactly "${nonce}". Use write_file with path="${filename}" and content="${nonce}". Do not choose another filename and do not use shell commands. After writing it, briefly confirm completion. HOSTED_FILE=${filename} HOSTED_MARKER=${nonce}`;
  const deadline = Date.now() + 180_000;
  const remaining = () => Math.max(1, deadline - Date.now());
  const box = page.getByPlaceholder(/Ask the coworker/);
  await box.fill(prompt);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const approve = page.getByRole("button", { name: /^Allow(?: once)?$/ });
  await expect(approve).toBeVisible({ timeout: remaining() });
  expect(events.slice(start).some(event => event.type === "tool_finished" && event.data?.name === "write_file")).toBe(false);
  await approve.click({ timeout: remaining() });
  await expect.poll(() => events.slice(start).some(event => event.type === "turn_done"), { timeout: remaining() }).toBe(true);
  const turn = events.slice(start);
  expect(turn.some(event => event.type === "tool_finished" && event.data?.name === "write_file" && ["ok", "done"].includes(event.data?.status))).toBe(true);
  expect(turn.some(event => event.type === "assistant_message" && event.data?.text?.trim() && !event.data?.tool_calls?.length)).toBe(true);
  expect(turn.some(event => event.type === "sandbox_ready" && event.data?.provider === "openshell" && event.data?.enforcement === "full")).toBe(true);
  expect(turn.filter(event => event.type === "error")).toEqual([]);
  const ready = events.filter(event => event.type === "ready").at(-1)?.data;
  expect(ready?.model).toBe(manifest.model);
  const session = ready?.session_id as string;
  expect(session).toBeTruthy();
  const disk = control(manifest, { action: "file", user: account.username, filename });
  expect(disk.content.replace(/\n$/, "")).toBe(nonce);
  expect(disk.path.startsWith((options.workspace || account.home + "/workspace") + "/")).toBe(true);
  const query = new URLSearchParams({ session, path: disk.path });
  const url = manifest.origin + "/web/artifacts/download?" + query;
  const download = await page.request.get(url);
  expect(download.ok()).toBe(true);
  expect((await download.text()).replace(/\n$/, "")).toBe(nonce);
  const hash = new URL(page.url()).hash;
  await page.reload();
  await expect(page.getByPlaceholder(/Ask the coworker/)).toBeVisible();
  expect(new URL(page.url()).hash).toBe(hash);
  const stored = await (await page.request.get(manifest.origin + `/v1/sessions/${encodeURIComponent(session)}/messages`)).json();
  expect(stored.messages.some((message: any) => message.role === "assistant" && message.content)).toBe(true);
  expect(stored.messages.some((message: any) => message.role === "tool")).toBe(true);
  expect((await page.request.get(url)).ok()).toBe(true);
  return { session, nonce, url, filename, path: disk.path, content: disk.content };
}

