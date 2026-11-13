"use client";

import { useParams } from "next/navigation";

import { IncidentPage } from "@/components/domain/incidents/incident-page";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <IncidentPage id={id} />;
}
