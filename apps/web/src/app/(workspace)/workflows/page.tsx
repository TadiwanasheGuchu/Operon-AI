import type { Metadata } from "next";

import { RequestsPage } from "@/components/domain/workflows/requests-page";

export const metadata: Metadata = { title: "Purchase requests" };

export default function Page() {
  return <RequestsPage />;
}
