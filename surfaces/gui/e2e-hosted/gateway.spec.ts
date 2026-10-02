import { test, expect, chromium, firefox, type BrowserContext } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { control, login, work, type Manifest, type Event } from "./helpers";

test("HTTPS gateway: two independent browsers, real engines, artifacts and expiry", async ({}, info) => {
  const path = process.env.HOSTED_TEST_MANIFEST;
  if (!path) throw new Error("HOSTED_TEST_MANIFEST is required; see docs/headless-vm-ui.md");
  const manifest = JSON.parse(readFileSync(path, "utf8")) as Manifest;
  const live = process.env.HOSTED_TEST_LLM === "1";
  expect(manifest.mode).toBe(live ? "llm" : "fixture");
  expect(manifest.engine_tokens).toHaveLength(2);
  const browsers = [await chromium.launch(), await firefox.launch()];
  const contexts: BrowserContext[] = [];
  const observations: string[] = [];
  const responses: Promise<void>[] = [];
  const eventLogs: Event[][] = [[], []];
  try {
    for (let index = 0; index < browsers.length; index++) {
      const context = await browsers[index].newContext({ ignoreHTTPSErrors: true });
      contexts.push(context);
      await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
      const page = await context.newPage();
      page.on("request", request => observations.push(request.url(), JSON.stringify(request.headers()), request.postData() || ""));
      page.on("response", response => responses.push(response.text().then(text => { observations.push(text, JSON.stringify(response.headers())); }).catch(() => {})));
      page.on("websocket", socket => {
        observations.push(socket.url());
        socket.on("framesent", frame => observations.push(String(frame.payload)));
        socket.on("framereceived", frame => {
          observations.push(String(frame.payload));
          if (socket.url().includes("/ws/session/")) {
            try {
              const event = JSON.parse(String(frame.payload)) as Event;
              eventLogs[index].push(event);
              if (["sandbox_ready", "permission_required", "tool_finished", "turn_done", "error"].includes(event.type)) {
                console.log(`${manifest.accounts[index].username}: ${event.type} ${event.data?.name || ""} ${event.data?.status || ""}`);
              }
            } catch { /* binary frames */ }
          }
        });
      });
      await login(page, manifest, manifest.accounts[index]);
      console.log(`Signed in ${manifest.accounts[index].username} in ${index === 0 ? "Chromium" : "Firefox"}`);
    }
    const pages = contexts.map(context => context.pages()[0]);
    const outcomes = await Promise.all(pages.map((page, index) => work(page, manifest, manifest.accounts[index], eventLogs[index])));
    console.log(`Both ${manifest.mode} model turns produced verified, persisted account-owned files`);
    for (let index = 0; index < 2; index++) {
      const other = outcomes[1 - index];
      expect((await pages[index].request.get(other.url)).status()).toBe(404);
      const response = await pages[index].request.get(manifest.origin + `/v1/sessions/${other.session}/messages`);
      expect(await response.text()).not.toContain(other.nonce);
      const storage = await pages[index].evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
      observations.push(storage, await pages[index].content());
    }
    control(manifest, { action: "expire", user: "alice" });
    await expect(pages[0]).toHaveURL(manifest.origin + "/web/login", { timeout: 25_000 });
    expect((await pages[1].request.get(manifest.origin + "/web/auth/session")).ok()).toBe(true);
    await work(pages[1], manifest, manifest.accounts[1], eventLogs[1]);
    await Promise.all(responses);
    for (const token of manifest.engine_tokens) {
      expect(observations.some(value => value.includes(token)), "engine launch token disclosed to browser").toBe(false);
    }
  } finally {
    for (let index = 0; index < contexts.length; index++) {
      const eventsPath = info.outputPath(`events-${manifest.accounts[index].username}.json`);
      writeFileSync(eventsPath, JSON.stringify(eventLogs[index], null, 2));
      await info.attach(`events-${manifest.accounts[index].username}`, { path: eventsPath, contentType: "application/json" });
      await contexts[index].tracing.stop({ path: info.outputPath(`trace-${manifest.accounts[index].username}.zip`) });
      await contexts[index].close();
    }
    for (const browser of browsers) await browser.close();
  }
});
