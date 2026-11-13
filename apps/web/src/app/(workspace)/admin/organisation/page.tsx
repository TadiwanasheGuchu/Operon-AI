import type { Metadata } from "next";

import { OrganisationPage } from "@/components/domain/admin/organisation-page";

export const metadata: Metadata = { title: "Organisation" };

export default function Page() {
  return <OrganisationPage />;
}
