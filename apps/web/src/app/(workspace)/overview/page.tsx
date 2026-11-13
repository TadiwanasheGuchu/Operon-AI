import type { Metadata } from "next";

import { CommandCentre } from "@/components/domain/dashboard/command-centre";

export const metadata: Metadata = { title: "Overview" };

export default function OverviewPage() {
  return <CommandCentre />;
}
