import type { Metadata } from "next";

import { ControlRoom } from "@/components/control-room/control-room";

export const metadata: Metadata = {
  title: "Control room",
};

export default function HomePage() {
  return <ControlRoom />;
}
