import { test, expect, HOSTED_WORKSPACE, seedMachines } from "./fixtures";
import type { Page } from "@playwright/test";

test.use({ hosted: true });

async function settings(page: Page, tab?: string) {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  if (tab) await page.getByRole("button", { name: tab, exact: true }).click();
}

async function folder(page: Page) {
  await page.getByRole("button", { name: "New session", exact: true }).click();
  await page.getByTestId("folder-chip").click();
  const input = page.getByPlaceholder("Path inside your home on this VM");
  await expect(input).toHaveValue(HOSTED_WORKSPACE);
  return input;
}

test("hosted account shows username and VM path; sign out returns to password login", async ({ page }) => {
  await settings(page, "Account");
  await expect(page.getByTestId("account-row")).toContainText("alice");
  const card = page.getByTestId("web-account-card");
  await expect(card).toContainText("alice");
  await expect(card).toContainText(HOSTED_WORKSPACE);
  const request = page.waitForRequest("**/web/auth/logout");
  await card.getByRole("button", { name: "Sign out", exact: true }).click();
  expect((await request).headers()["x-csrf-token"]).toBe("hosted-test-csrf");
  await expect(page).toHaveURL(/\/web\/login$/);
});

test("hosted workspace uses typed paths and recent folders; errors stay in the form", async ({ page }) => {
  const native: string[] = [];
  page.on("request", request => { if (request.url().includes("/workspaces/pick")) native.push(request.url()); });
  await page.goto("/");
  const input = await folder(page);
  for (const [path, message] of [
    ["/srv/openworker/bob/workspace", "this machine only works under"],
    [HOSTED_WORKSPACE + "/missing", "folder does not exist"],
    [HOSTED_WORKSPACE + "/file.txt", "not a directory"],
  ]) {
    await input.fill(path);
    await input.press("Enter");
    await expect(page.getByText(message, { exact: false })).toBeVisible();
    await expect(input).toBeVisible();
  }
  await input.fill(HOSTED_WORKSPACE + "/project");
  await input.press("Enter");
  await expect(page.getByTestId("folder-chip")).toContainText("project");
  await page.reload();
  await folder(page);
  await page.getByRole("button", { name: "project " + HOSTED_WORKSPACE + "/project" }).click();
  await expect(page.getByTestId("folder-chip")).toContainText("project");
  expect(native).toEqual([]);
});

test("expired hosted session redirects when a workspace request returns 401", async ({ page }) => {
  await page.goto("/");
  const input = await folder(page);
  await page.route("**/web/auth/session", route => route.fulfill({ status: 401, json: { error: "authentication required" } }));
  await page.route("**/v1/workspaces/open", route => route.fulfill({ status: 401, json: { error: "authentication required" } }));
  await input.press("Enter");
  await expect(page).toHaveURL(/\/web\/login$/);
});

test("hosted artifact menu downloads through the gateway without native reveal", async ({ page }) => {
  const native: string[] = [];
  page.on("request", request => { if (request.url().endsWith("/artifacts/reveal")) native.push(request.url()); });
  await page.goto("/");
  await page.getByPlaceholder(/Ask the coworker/).fill("show the report");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByTestId("rail-toggle-artifacts").click();
  await page.locator(".artifact-row", { hasText: "security-review.html" }).click();
  await page.getByTestId("artifact-more").click();
  await expect(page.getByTestId("artifact-reveal")).toHaveCount(0);
  await expect(page.getByTestId("artifact-open-browser")).toHaveCount(0);
  const download = page.waitForEvent("download");
  await page.getByTestId("artifact-download").click();
  const result = await download;
  const url = new URL(result.url());
  expect(url.searchParams.get("path")).toBe("reports/security-review.html");
  expect(url.searchParams.get("session")).toBeTruthy();
  expect(result.suggestedFilename()).toBe("security-review.html");
  expect(native).toEqual([]);
});

test("hosted skill files describe their VM location without Show folder", async ({ page }) => {
  await settings(page, "Skills");
  await expect(page.getByText("html-to-markdown", { exact: true })).toBeVisible();
  await expect(page.getByTitle("Show folder", { exact: true })).toHaveCount(0);
  await expect(page.getByTitle(/Files live on ⌂ Hosted VM/)).toBeVisible();
});

test("hosted enrollment uses the account URL and public instructions; expiry can be renewed", async ({ page }) => {
  let count = 0;
  let renewed = false;
  const clockTime = new Date("2026-10-02T10:00:00Z");
  await page.clock.install({ time: clockTime });
  await page.route("**/v1/remote/arm", route => {
    if (route.request().method() === "DELETE") return route.fulfill({ json: { armed: false } });
    count++;
    return route.fulfill({ json: {
      join_url: `https://worker.example.test/h/${"a".repeat(32)}/j/hosted-enrollment-${count}`,
      expires_at: clockTime.getTime() / 1000 + (renewed ? 600 : 2),
    } });
  });
  await settings(page, "Machines");
  await expect(page.getByText("Hosted VM", { exact: true })).toBeVisible();
  await page.getByText("Add a machine…", { exact: true }).click();
  await expect(page.getByTestId("join-command")).toContainText("https://worker.example.test/h/");
  await expect(page.getByText(/ssh -N -R/)).toHaveCount(0);
  await expect(page.getByText("Run this on the machine:", { exact: true })).toBeVisible();
  await page.clock.runFor(3_000);
  await expect(page.getByText("Enrollment window expired.", { exact: true })).toBeVisible();
  const previous = count;
  renewed = true;
  await page.getByRole("button", { name: "Re-arm", exact: true }).click();
  await expect.poll(() => count).toBeGreaterThan(previous);
  await expect(page.getByTestId("join-command")).toContainText(`hosted-enrollment-${count}`);
  await expect(page.getByTestId("token-countdown")).toBeVisible();
});

test("hosted enrollment detects an external machine and labels local selection Hosted VM", async ({ page }) => {
  const seeded = await seedMachines(page, [{ id: "existing", name: "already-connected", fingerprint: "1234567890abcdef", connected: true,
    app_version: "0.2.0", created_at: Date.now() / 1000, last_seen: Date.now() / 1000 }]);
  await settings(page, "Machines");
  await page.getByText("Add a machine…", { exact: true }).click();
  await expect(page.getByTestId("machine-scope-picker").locator("option[value=\"\"]")).toHaveText("⌂ Hosted VM");
  seeded.join({ id: "external", name: "outside-vm", fingerprint: "1234567890abcdef", connected: true,
    app_version: "0.2.0", created_at: Date.now() / 1000, last_seen: Date.now() / 1000 });
  await expect(page.getByTestId("join-success")).toContainText("outside-vm joined");
  await page.getByRole("button", { name: "Back to app", exact: true }).click();
  await page.getByRole("button", { name: "New session", exact: true }).click();
  await expect(page.getByTestId("runson-chip")).toContainText("Hosted VM");
});

test("failed enrollment shows a retry and does not offer an invalid command to copy", async ({ page }) => {
  let unavailable = true;
  await page.route("**/v1/remote/arm", route => unavailable
    ? route.fulfill({ status: 503, json: { error: "engine unavailable" } })
    : route.fulfill({ json: {
      join_url: `https://worker.example.test/h/${"a".repeat(32)}/j/recovered-enrollment-token`,
      expires_at: Date.now() / 1000 + 600,
    } }));
  await settings(page, "Machines");
  await page.getByText("Add a machine…", { exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Could not create a join link. Try again.");
  await expect(page.getByRole("button", { name: "Copy", exact: true })).toBeDisabled();
  unavailable = false;
  await page.getByRole("button", { name: "Re-arm", exact: true }).click();
  await expect(page.getByTestId("join-command")).toContainText("recovered-enrollment-token");
  await expect(page.getByRole("alert")).toHaveCount(0);
});
