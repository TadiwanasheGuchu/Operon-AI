import type { Metadata } from "next";

import { IntelligenceSettingsPage } from "@/components/domain/intelligence/settings-page";

export const metadata: Metadata = { title: "Detectors and AI" };

export default function Page() {
  return <IntelligenceSettingsPage />;
}
