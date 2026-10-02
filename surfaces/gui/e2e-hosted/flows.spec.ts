import { test, expect, chromium, firefox, type Page, type BrowserContext } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { readFileSync, writeFileSync, mkdtempSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { control, login, work, newSession, type Manifest, type Account, type Event } from "./helpers";

type Joiner = { process: ChildProcess; output: string; state: string; root: string };

async function settings(page: Page, tab: string) {
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: tab, exact: true }).click();
}

async function machineLink(page: Page) {
  await settings(page, "Machines");
  await expect(page.getByText("Hosted VM", { exact: true })).toBeVisible();
  await page.getByText("Add a machine…", { exact: true }).click();
  await expect(page.getByTestId("join-command")).toContainText("openworker join https://");
  await expect(page.getByText(/ssh -N -R/)).toHaveCount(0);
  await expect(page.getByText("Run this on the machine:", { exact: true })).toBeVisible();
  // This gate tests routing, not provision of model credentials to the joiner.
  const provision = page.getByTestId("provision-defaults");
  if (await provision.count()) await provision.uncheck();
  const command = await page.getByTestId("join-command").textContent();
  const url = command?.match(/^openworker join (https:\/\/\S+) --name=my-box$/)?.[1];
  expect(url, "UI must display a valid public HTTPS join command").toBeTruthy();
  return url!;
}

function startJoiner(root: string, url: string | null, name: string, state?: string): Joiner {
  const python = process.env.HOSTED_TEST_EXTERNAL_PYTHON;
  const certificate = process.env.HOSTED_TEST_CA;
  if (!python || !certificate) throw new Error("HOSTED_TEST_EXTERNAL_PYTHON and HOSTED_TEST_CA are required");
  const directory = state || join(root, name, "state");
  const base = join(directory, "..");
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  mkdirSync(join(base, "workspace"), { recursive: true, mode: 0o700 });
  const env = Object.fromEntries(["PATH", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR"].flatMap(key =>
    process.env[key] ? [[key, process.env[key]!]] : []));
  const child = spawn(python, ["-m", "coworker.cli", ...(url ? ["join", url, "--name", name] : ["up"])], {
    env: { ...env, SSL_CERT_FILE: certificate, COWORKER_STATE_DIR: directory,
      OPENWORKER_BASE_DIR: base, COWORKER_SCRATCH_BASE: join(base, "workspace"), PYTHONUNBUFFERED: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const joiner = { process: child, output: "", state: directory, root: base };
  child.stdout!.on("data", chunk => { joiner.output += String(chunk); });
  child.stderr!.on("data", chunk => { joiner.output += String(chunk); });
  child.on("error", error => { joiner.output += error.message; });
  return joiner;
}

function exited(joiner: Joiner, timeout = 30_000): Promise<number | null> {
  if (joiner.process.exitCode !== null || joiner.process.signalCode !== null)
    return Promise.resolve(joiner.process.exitCode);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { reject(new Error("external CLI did not exit within its deadline")); }, timeout);
    joiner.process.once("exit", code => { clearTimeout(timer); resolve(code); });
    joiner.process.once("error", error => { clearTimeout(timer); reject(error); });
  });
}

async function stop(joiner: Joiner) {
  if (joiner.process.exitCode !== null || joiner.process.signalCode !== null) return;
  joiner.process.kill("SIGINT");
  try { await exited(joiner, 10_000); }
  catch { joiner.process.kill("SIGKILL"); await exited(joiner, 5_000); }
}

async function machines(page: Page, manifest: Manifest): Promise<any[]> {
  const response = await page.request.get(manifest.origin + "/v1/machines");
  expect(response.ok()).toBe(true);
  return (await response.json()).machines;
}

async function workspace(page: Page, account: Account, peer: Account) {
  await newSession(page);
  await page.getByTestId("folder-chip").click();
  const input = page.getByPlaceholder("Path inside your home on this VM");
  await expect(input).toHaveValue(account.home + "/workspace");
  for (const [path, error] of [
    [account.home + "/workspace/missing", "folder does not exist"],
    [account.home + "/workspace/file.txt", "not a directory"],
    [peer.home + "/workspace", "only works under"],
    [account.home + "/workspace/escape", "only works under"],
  ]) {
    await input.fill(path);
    await input.press("Enter");
    await expect(page.getByText(error, { exact: false })).toBeVisible();
  }
  const project = account.home + "/workspace/phase4-project";
  await input.fill(project);
  await input.press("Enter");
  await expect(page.getByTestId("folder-chip")).toContainText("phase4-project");
  return project;
}

async function downloadFromViewer(page: Page, outcome: Awaited<ReturnType<typeof work>>) {
  const show = page.getByRole("button", { name: "Show side panel", exact: true });
  if (await show.isVisible()) await show.click();
  await page.getByTestId("rail-toggle-files").click();
  await page.getByTitle(dirname(outcome.path), { exact: true }).click();
  await page.getByTestId("artifact-folder").locator(".artifact-folder-row", { hasText: outcome.filename }).click();
  await expect(page.locator(".artifact-viewer")).toContainText(outcome.nonce);
  await page.getByTestId("artifact-more").click();
  await expect(page.getByTestId("artifact-reveal")).toHaveCount(0);
  const pending = page.waitForEvent("download");
  await page.getByTestId("artifact-download").click();
  const download = await pending;
  expect(download.suggestedFilename()).toBe(outcome.filename);
  const path = await download.path();
  expect(path).toBeTruthy();
  expect(readFileSync(path!, "utf8")).toBe(outcome.content);
}

test("password hosted flows: workspaces, UI downloads, external machine joins and expiry", async ({}, info) => {
  const manifestPath = process.env.HOSTED_TEST_MANIFEST;
  if (!manifestPath) throw new Error("HOSTED_TEST_MANIFEST is required");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as Manifest & { flows: boolean };
  expect(manifest.flows).toBe(true);
  expect(manifest.mode).toBe("fixture");
  expect(manifest.engine_tokens).toHaveLength(2);
  if (!process.env.HOSTED_TEST_SSH_RUNNER) throw new Error("run this gate on a workstation outside the fixture VM using HOSTED_TEST_SSH_RUNNER");
  const root = mkdtempSync(join(tmpdir(), "openworker-phase4-joiner-"));
  const browsers = [await chromium.launch(), await firefox.launch()];
  const contexts: BrowserContext[] = [];
  const joiners: Joiner[] = [];
  const events: Event[][] = [[], []];
  const observations: string[] = [];
  const responses: Promise<void>[] = [];
  const native: string[] = [];
  const secrets = [...manifest.engine_tokens, ...manifest.accounts.map(account => account.password)];
  try {
    for (let index = 0; index < browsers.length; index++) {
      const context = await browsers[index].newContext({ ignoreHTTPSErrors: true });
      context.setDefaultTimeout(30_000);
      context.setDefaultNavigationTimeout(30_000);
      contexts.push(context);
      await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
      const page = await context.newPage();
      page.on("request", request => {
        observations.push(request.url(), JSON.stringify(request.headers()), request.postData() || "");
        if (/\/workspaces\/pick|\/artifacts\/reveal|\/skills\/[^/]+\/reveal|\/mcp\/config\/reveal/.test(request.url())) native.push(request.url());
      });
      page.on("response", response => responses.push(response.text().then(body => { observations.push(body); }).catch(() => {})));
      page.on("websocket", socket => {
        observations.push(socket.url());
        socket.on("framesent", frame => observations.push(String(frame.payload)));
        socket.on("framereceived", frame => {
          observations.push(String(frame.payload));
          if (socket.url().includes("/ws/session/")) {
            try { events[index].push(JSON.parse(String(frame.payload))); } catch { /* binary frame */ }
          }
        });
      });
      await login(page, manifest, manifest.accounts[index]);
      console.log(`Signed in ${manifest.accounts[index].username}`);
    }
    const pages = contexts.map(context => context.pages()[0]);
    const projects = await Promise.all(pages.map((page, index) => workspace(page, manifest.accounts[index], manifest.accounts[1 - index])));
    console.log("Both browsers selected confined VM projects and rejected invalid paths");
    const outcomes = await Promise.all(pages.map((page, index) => work(page, manifest, manifest.accounts[index], events[index], { startNewSession: false, workspace: projects[index] })));
    console.log("Both enforcing engines completed approved writes in the selected projects");
    await Promise.all(pages.map((page, index) => downloadFromViewer(page, outcomes[index])));
    for (let index = 0; index < pages.length; index++) {
      expect((await pages[index].request.get(outcomes[1 - index].url)).status()).toBe(404);
      const missing = new URL(outcomes[index].url);
      missing.searchParams.set("path", "missing.txt");
      expect((await pages[index].request.get(missing.href)).status()).toBe(404);
      await newSession(pages[index]);
      await pages[index].getByTestId("folder-chip").click();
      await pages[index].getByRole("button", { name: "phase4-project " + projects[index] }).click();
      await expect(pages[index].getByTestId("folder-chip")).toContainText("phase4-project");
    }
    console.log("Both browsers verified VM workspace boundaries, persisted recents and exact UI downloads");
    const joinUrl = await machineLink(pages[0]);
    expect(new URL(joinUrl).pathname.startsWith(`/h/${manifest.accounts[0].id}/j/`)).toBe(true);
    secrets.push(new URL(joinUrl).pathname.split("/").at(-1)!);
    const external = startJoiner(root, joinUrl, "phase4-external");
    joiners.push(external);
    await expect(pages[0].getByTestId("join-success")).toContainText("phase4-external joined");
    const row = (await machines(pages[0], manifest)).find(machine => machine.name === "phase4-external");
    expect(row?.connected).toBe(true);
    expect((await machines(pages[1], manifest)).some(machine => machine.id === row.id)).toBe(false);
    const auth = await (await pages[0].request.get(manifest.origin + "/web/auth/session")).json();
    const headers = { Origin: manifest.origin, "X-CSRF-Token": auth.csrf };
    const remotePath = external.root + "/workspace";
    const route = `/v1/machines/${row.id}/p/v1/workspaces/open`;
    const opened = await pages[0].request.post(manifest.origin + route, { headers, data: { path: remotePath } });
    expect(opened.ok()).toBe(true);
    expect(await opened.json()).toMatchObject({ ok: true, path: remotePath });
    expect((await pages[1].request.get(manifest.origin + `/v1/machines/${row.id}/p/v1/health`)).status()).toBe(404);
    await pages[0].getByRole("button", { name: "Back to app", exact: true }).click();
    await newSession(pages[0]);
    await pages[0].getByTestId("runson-chip").click();
    await pages[0].getByRole("button", { name: "⌂ phase4-external", exact: false }).click();
    await pages[0].getByTestId("folder-chip").click();
    await pages[0].getByTestId("machine-folder-input").fill(remotePath);
    await pages[0].getByTestId("machine-folder-check").click();
    await expect(pages[0].getByTestId("machine-folder-use")).toBeEnabled();
    await pages[0].getByTestId("machine-folder-use").click();
    await stop(external);
    await expect.poll(async () => (await machines(pages[0], manifest)).find(machine => machine.id === row.id)?.connected).toBe(false);
    const reconnected = startJoiner(root, null, "phase4-external", external.state);
    joiners.push(reconnected);
    await expect.poll(async () => (await machines(pages[0], manifest)).find(machine => machine.id === row.id)?.connected).toBe(true);
    expect(JSON.parse(readFileSync(join(external.state, "remote.json"), "utf8")).machine_id).toBe(row.id);
    for (const [name, url] of [
      ["invalid", manifest.origin + `/h/${manifest.accounts[0].id}/j/` + "invalid-token-".repeat(3)],
      ["reused", joinUrl],
      ["wrong-account", joinUrl.replace(manifest.accounts[0].id, manifest.accounts[1].id)],
    ]) {
      const rejected = startJoiner(root, url, name);
      joiners.push(rejected);
      expect(await exited(rejected), `${name} enrollment must fail`).toBe(1);
      expect(rejected.output).toContain("not-enrolled");
    }
    const disarmedUrl = await machineLink(pages[0]);
    secrets.push(new URL(disarmedUrl).pathname.split("/").at(-1)!);
    await Promise.all([
      pages[0].waitForResponse(response => response.url().endsWith("/v1/remote/arm") && response.request().method() === "DELETE"),
      pages[0].getByRole("button", { name: "Back to app", exact: true }).click(),
    ]);
    const disarmed = startJoiner(root, disarmedUrl, "disarmed");
    joiners.push(disarmed);
    expect(await exited(disarmed)).toBe(1);
    expect(disarmed.output).toContain("not-enrolled");
    console.log("External CLI enrollment, signed reconnect, peer isolation and rejected tokens passed");
    control(manifest, { action: "expire", user: "alice" });
    await pages[0].reload();
    await expect(pages[0]).toHaveURL(url => url.origin === manifest.origin && url.pathname === "/web/login");
    expect((await pages[0].request.get(outcomes[0].url)).status()).toBe(401);
    await work(pages[1], manifest, manifest.accounts[1], events[1]);
    await settings(pages[1], "Account");
    await expect(pages[1].getByTestId("web-account-card")).toContainText(manifest.accounts[1].home + "/workspace");
    await pages[1].getByTestId("web-account-card").getByRole("button", { name: "Sign out", exact: true }).click();
    await expect(pages[1]).toHaveURL(url => url.origin === manifest.origin && url.pathname === "/web/login");
    expect((await pages[1].request.get(manifest.origin + "/web/auth/session")).status()).toBe(401);
    await Promise.all(responses);
    expect(native, "hosted product flows called a native UI endpoint").toEqual([]);
    for (const token of manifest.engine_tokens)
      expect(observations.some(value => value.includes(token)), "engine token disclosed to browser").toBe(false);
    console.log("Password logout, independent expiry, continued peer work and token non-disclosure passed");
  } finally {
    for (const joiner of joiners) await stop(joiner);
    for (let index = 0; index < contexts.length; index++) {
      writeFileSync(info.outputPath(`events-${manifest.accounts[index].username}.json`), JSON.stringify(events[index], null, 2));
      await contexts[index].tracing.stop({ path: info.outputPath(`trace-${manifest.accounts[index].username}.zip`) });
      await contexts[index].close();
    }
    for (const browser of browsers) await browser.close();
    const sanitized = joiners.map(joiner => secrets.reduce((output, secret) => output.replaceAll(secret, "[redacted]"), joiner.output));
    writeFileSync(info.outputPath("external-joiners.log"), sanitized.join("\n"));
    rmSync(root, { recursive: true, force: true });
  }
});
