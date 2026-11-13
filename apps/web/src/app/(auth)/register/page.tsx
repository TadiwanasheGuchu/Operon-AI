import type { Metadata } from "next";

import { RegisterForm } from "@/components/domain/auth/register-form";

export const metadata: Metadata = { title: "Create your organisation" };

export default function RegisterPage() {
  return <RegisterForm />;
}
