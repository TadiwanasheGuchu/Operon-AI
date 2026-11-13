/**
 * The organisation the user is working in. Per-viewer convenience stored in localStorage;
 * the API re-verifies membership on every request, so a tampered value only yields a 404.
 */
const KEY = "operon.activeOrganisation";
const EVENT = "operon:organisation";

let memory: string | null = null;

export function getActiveOrganisationId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(KEY) ?? memory;
  } catch {
    return memory;
  }
}

export function setActiveOrganisationId(id: string | null): void {
  memory = id;
  try {
    if (id) window.localStorage.setItem(KEY, id);
    else window.localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: falls back to in-memory for this tab */
  }
  window.dispatchEvent(new Event(EVENT));
}

export function subscribeActiveOrganisation(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(EVENT, onChange);
  };
}
