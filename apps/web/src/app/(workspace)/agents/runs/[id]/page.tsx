"use client";

import { useParams } from "next/navigation";

import { RunPage } from "@/components/domain/agents/run-page";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <RunPage id={id} />;
}
