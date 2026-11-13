import type { Metadata } from "next";

import { PolicyPage } from "@/components/domain/workflows/policy-page";

export const metadata: Metadata = { title: "Approval policy" };

export default function Page() {
  return <PolicyPage />;
}
