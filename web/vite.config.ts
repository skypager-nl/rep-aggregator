import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base "./" + HashRouter: the app is served under Home Assistant's ingress
// prefix (/api/hassio_ingress/<token>/), so every URL must be relative.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8099",
      "/photos": "http://localhost:8099",
    },
  },
});
