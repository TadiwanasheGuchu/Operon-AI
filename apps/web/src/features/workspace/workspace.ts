/**
 * Workspace context: signed-in user, active organisation and what they may do there.
 * Built from GET /auth/session and /organisations/current.
 */
import type { Permission } from "@/features/session/types";

export interface WorkspaceOrganisation {
  id: string;
  name: string;
  initials: string;
  roleName: string;
  isDemo: boolean;
}

export interface Workspace {
  organisation: WorkspaceOrganisation;
  organisations: WorkspaceOrganisation[];
  user: { name: string; initials: string; role: string; email: string; mfaEnabled: boolean };
  can: (permission: Permission) => boolean;
}

export function initials(name: string): string {
  // First letters of the first two words, ignoring symbols ("Harbour & Vale" -> "HV").
  const words = name.trim().split(/\s+/).filter((w) => /^[\p{L}\p{N}]/u.test(w));
  const letters = words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? "").slice(0, 2);
  return letters.toUpperCase() || "—";
}
