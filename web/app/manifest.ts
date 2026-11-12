import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "FINN",
    short_name: "FINN",
    description: "A daily briefing on your portfolio: what changed, so what, who can help.",
    start_url: "/",
    display: "standalone",
    background_color: "#fbfaf8",
    theme_color: "#fbfaf8",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  };
}
