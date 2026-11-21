<script setup lang="ts">
import { withBase } from "vitepress";
</script>

<template>
  <div class="rc-404">
    <div>
      <img :src="withBase('/art/ghost-800.webp')" alt="" width="800" height="704">
      <span class="tag">reidcc · no gate here</span>
      <a :href="withBase('/docs/install')">back to docs</a>
    </div>
  </div>
</template>
