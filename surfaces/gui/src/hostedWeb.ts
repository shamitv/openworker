/** Browser session state for the opt-in headless VM gateway.
 * The engine token never enters this module or the browser bundle. */
type WebSession = {
  user?: string | { username?: string };
  csrf?: string;
  must_change?: boolean;
  workspace_root?: string;
};

let session: WebSession | null = null;

export const isHostedWeb = (): boolean => (globalThis as any).__COWORKER_WEB__ === true;
export const webCsrfToken = (): string => session?.csrf || "";
export const webUsername = (): string =>
  typeof session?.user === "string" ? session.user : session?.user?.username || "";
export const webWorkspaceRoot = (): string => session?.workspace_root || "";

export function redirectToWebLogin(): void {
  if (isHostedWeb()) window.location.replace("/web/login");
}

/** Runs before React renders. A missing or expired browser session cannot boot the UI. */
export async function initHostedWeb(): Promise<void> {
  if (!isHostedWeb()) return;
  const res = await globalThis.fetch("/web/auth/session", {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (res.status === 401) {
    redirectToWebLogin();
    await new Promise<never>(() => {});
  }
  if (!res.ok) throw new Error(`Browser session unavailable (${res.status})`);
  const current = (await res.json()) as WebSession;
  if (current.must_change) {
    window.location.replace("/web/change-password");
    await new Promise<never>(() => {});
  }
  if (!current.csrf || !current.user) throw new Error("Incomplete browser session");
  session = current;
}

export async function webSignOut(): Promise<void> {
  if (!isHostedWeb()) return;
  const res = await globalThis.fetch("/web/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": webCsrfToken() },
  });
  if (!res.ok && res.status !== 401) throw new Error("Could not sign out");
  session = null;
  redirectToWebLogin();
}
