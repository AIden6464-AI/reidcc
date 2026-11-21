import { defineConfig } from "vite";

export default defineConfig({
  clearScreen: false,
  build: {
    outDir: "dist", emptyOutDir: true, target: "es2022", assetsInlineLimit: 0,
    // the launcher, its mini pod (vision v1 §1), and the session window (vision v1 §2)
    rollupOptions: { input: { main: "index.html", session: "session.html", group: "group.html", pod: "pod.html" } },
  },
});
