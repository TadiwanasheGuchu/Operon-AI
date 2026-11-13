"use client";

import { createContext, useContext } from "react";

import type { Workspace } from "./workspace";

export interface WorkspaceActions {
  switchOrganisation: (id: string) => void;
  signOut: () => Promise<void>;
}

const Ctx = createContext<{ workspace: Workspace; actions: WorkspaceActions } | null>(null);

export const WorkspaceProvider = Ctx.Provider;

export function useWorkspace() {
  const value = useContext(Ctx);
  if (!value) throw new Error("useWorkspace must be used inside the workspace layout");
  return value;
}
