// VitePress's default theme, re-skinned with the app's tokens, plus the landing page and the 404.
import DefaultTheme from "vitepress/theme";
import { h } from "vue";
import { useData } from "vitepress";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/geist-mono/latin-400.css";
import "@fontsource/geist-mono/latin-500.css";
import "./tokens.css";
import "./theme.css";
import "./home.css";
import Home from "./Home.vue";
import NotFound from "./NotFound.vue";

export default {
  extends: DefaultTheme,
  Layout: () => {
    const { theme } = useData();
    return h(DefaultTheme.Layout, null, {
      "not-found": () => h(NotFound),
      // right of the top bar: the version, read from rs\Cargo.toml at build time
      "nav-bar-content-after": () => h("span", { class: "rc-ver" }, `v${theme.value.reidcc.version} · windows`),
    });
  },
  enhanceApp({ app }) {
    app.component("Home", Home);
  },
};
