import type { Metadata } from "next";

import { AuditPage } from "@/components/domain/admin/audit-page";

export const metadata: Metadata = { title: "Audit log" };

export default function Page() {
  return <AuditPage />;
}
