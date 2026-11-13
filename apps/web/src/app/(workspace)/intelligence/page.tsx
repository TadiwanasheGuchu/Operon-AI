import type { Metadata } from "next";

import { IntelligencePage } from "@/components/domain/intelligence/intelligence-page";

export const metadata: Metadata = { title: "Intelligence" };

export default function Page() {
  return <IntelligencePage />;
}
