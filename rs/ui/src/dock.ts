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
  bindRig();
  void view.listen<Look>("dock-look", ({ payload }) => {
    body.dataset.phase = payload.phase;
    if (payload.phase !== "settle") body.dataset.edge = payload.side ?? "";
    body.classList.toggle("moving", payload.phase === "drag");
  });
  // listen first, then ask: a pane snapped before this page loaded (a rig) never heard dock-grouped
  void view.listen<boolean>("dock-grouped", ({ payload }) => body.classList.toggle("grouped", payload))
    .then(() => invoke<boolean>("dock_grouped"))
    .then((grouped) => { if (grouped) body.classList.add("grouped"); });
}

/** The frame header's save rig (vision v1 §5): name it, Enter saves, Escape cancels. */
function bindRig() {
  const button = document.getElementById("rig");
  const name = document.getElementById("rigname") as HTMLInputElement | null;
  const note = document.getElementById("rignote");
  if (!button || !name || !note) return;
  let clear = 0;
  const say = (text: string, error = false) => {
    note.textContent = text;
    note.classList.toggle("error", error);
    clearTimeout(clear);
    if (text) clear = window.setTimeout(() => (note.textContent = ""), 4000);
  };
  button.addEventListener("click", () => {
    say("");
    name.hidden = false;
    name.focus();
    name.select();
  });
  name.addEventListener("keydown", async (event) => {
    if (event.key === "Escape") name.hidden = true;
    if (event.key !== "Enter") return;
    try {
      say(await invoke<string>("rig_save", { name: name.value }));
      name.hidden = true;
    } catch (error) {
      say(String(error), true);
    }
  });
  name.addEventListener("blur", () => (name.hidden = true));
}
