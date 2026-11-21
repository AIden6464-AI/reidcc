import { invoke } from "@tauri-apps/api/core";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { PACE } from "./gate";

type Look = { side: "left" | "right" | "top" | "bottom" | null; phase: string };

export function bindDock() {
  const body = document.body;
  const view = getCurrentWebview();
  body.style.setProperty("--gate-pace", String(PACE));
  const header = document.querySelector("[data-pane-drag]");
  header?.addEventListener("pointerdown", (event) => {
    if ((event as PointerEvent).button === 0 && !(event.target as Element).closest("button, .detail")) {
      void invoke("dock_drag");
    }
  });
  header?.addEventListener("dblclick", (event) => {
    if (!body.classList.contains("grouped") && !(event.target as Element).closest("button, .detail")) {
      void invoke("dock_control", { action: "max" });
    }
  });
  for (const button of document.querySelectorAll<HTMLButtonElement>("[data-dock-action]")) {
    button.addEventListener("click", () => void invoke("dock_control", { action: button.id }));
  }
  void view.listen<Look>("dock-look", ({ payload }) => {
    body.dataset.phase = payload.phase;
    if (payload.phase !== "settle") body.dataset.edge = payload.side ?? "";
    body.classList.toggle("moving", payload.phase === "drag");
  });
  void view.listen<boolean>("dock-grouped", ({ payload }) => body.classList.toggle("grouped", payload));
}
