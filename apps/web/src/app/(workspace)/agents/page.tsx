import type { Metadata } from "next";

import { AgentsPage } from "@/components/domain/agents/agents-page";

export const metadata: Metadata = { title: "AI agents" };

export default function Page() {
  return <AgentsPage />;
}
