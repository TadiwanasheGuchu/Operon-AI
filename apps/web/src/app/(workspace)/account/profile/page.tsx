import type { Metadata } from "next";

import { ProfilePage } from "@/components/domain/account/profile-page";

export const metadata: Metadata = { title: "Profile" };

export default function Page() {
  return <ProfilePage />;
}
