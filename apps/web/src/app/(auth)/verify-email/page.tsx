import type { Metadata } from "next";
import { Suspense } from "react";

import { VerifyEmail } from "@/components/domain/auth/token-pages";

export const metadata: Metadata = { title: "Confirm your email" };

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmail />
    </Suspense>
  );
}
