import type { Metadata } from "next";

import { IncidentsPage } from "@/components/domain/incidents/incidents-page";

export const metadata: Metadata = { title: "Incidents" };

export default function Page() {
  return <IncidentsPage />;
}
