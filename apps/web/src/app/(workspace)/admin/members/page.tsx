import type { Metadata } from "next";

import { MembersPage } from "@/components/domain/admin/members-page";

export const metadata: Metadata = { title: "Members" };

export default function Page() {
  return <MembersPage />;
}
