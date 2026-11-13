"use client";

import { useParams } from "next/navigation";

import { ConnectionPage } from "@/components/domain/integrations/connection-page";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <ConnectionPage id={id} />;
}
