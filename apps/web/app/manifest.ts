import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "musematic",
    short_name: "musematic",
    description: "musematic workflow engine platform",
    start_url: "/home",
    scope: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#4f46e5",
    icons: [
      {
        src: "/icons/musematic-192.png",
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: "/icons/musematic-512.png",
        sizes: "512x512",
        type: "image/png",
      },
      {
        src: "/icons/musematic-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}

