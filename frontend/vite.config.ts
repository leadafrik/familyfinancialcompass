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
    build: {
      // react-pdf/renderer is ~1.5 MB minified and cannot be reduced further.
      // It is only loaded on-demand via dynamic import() at PDF generation time
      // so it does not affect initial page load. Raise the warning threshold to
      // avoid noise on a chunk we cannot (and do not need to) shrink.
      chunkSizeWarningLimit: 2000,
      rollupOptions: {
        output: {
          manualChunks: {
            // Isolate the heavy react-pdf bundle so it is only loaded on demand
            // (dynamic import at PDF generation time, not on initial page load).
            "pdf-renderer": ["@react-pdf/renderer"],
          },
        },
      },
    },
  };
});
