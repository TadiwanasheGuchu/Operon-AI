"use client";

import { useParams } from "next/navigation";

import { InsightPage } from "@/components/domain/intelligence/insight-page";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <InsightPage id={id} />;
}
