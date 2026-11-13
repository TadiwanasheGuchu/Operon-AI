import type { Metadata } from "next";
import { Suspense } from "react";

import { ResetPassword } from "@/components/domain/auth/token-pages";

export const metadata: Metadata = { title: "Choose a new password" };

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetPassword />
    </Suspense>
  );
}
