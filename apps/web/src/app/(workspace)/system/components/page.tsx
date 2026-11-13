import type { Metadata } from "next";

import { ComponentStates } from "@/components/domain/system/component-states";

export const metadata: Metadata = { title: "Component states" };

export default function ComponentStatesPage() {
  return <ComponentStates />;
}
