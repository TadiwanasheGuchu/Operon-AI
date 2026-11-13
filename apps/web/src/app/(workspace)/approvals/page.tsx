import type { Metadata } from "next";

import { ApprovalsPage } from "@/components/domain/workflows/approvals-page";

export const metadata: Metadata = { title: "Approvals" };

export default function Page() {
  return <ApprovalsPage />;
}
