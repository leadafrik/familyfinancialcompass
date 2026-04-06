import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

function normalizeBasePath(value: string | undefined): string {
  const trimmed = value?.trim();
  if (!trimmed) {
    return "/";
  }
  return `/${trimmed.replace(/^\/+|\/+$/g, "")}/`;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");

  return {
    base: normalizeBasePath(env.VITE_APP_BASE_PATH),
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: "https://family-financial-compass-4wwf7gusiq-ue.a.run.app",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
