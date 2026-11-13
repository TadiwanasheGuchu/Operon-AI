import type { Metadata } from "next";
import { Suspense } from "react";

import { InvitePage } from "@/components/domain/auth/invite-page";

export const metadata: Metadata = { title: "Invitation" };

export default function Invite() {
  return (
    <Suspense>
      <InvitePage />
    </Suspense>
  );
}
