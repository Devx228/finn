"use client";

import { useEffect } from "react";
import { warmUp } from "@/lib/api";

/** Pings /health on load so a sleeping backend starts waking immediately. */
export function WarmUp() {
  useEffect(() => warmUp(), []);
  return null;
}
