<template>
  <template v-if="menu.children && menu.children.length > 0">
    <a-sub-menu :key="menu.code">
      <template #title>
        <component :is="getIcon(menu.icon)" v-if="menu.icon" />
        <span>{{ menu.name }}</span>
      </template>
      <MenuItemRecursive
        v-for="child in menu.children"
        :key="child.code"
        :menu="child"
        :get-icon="getIcon"
      />
    </a-sub-menu>
  </template>
  <a-menu-item v-else :key="menu.code">
    <component :is="getIcon(menu.icon)" v-if="menu.icon" />
    <span>{{ menu.name }}</span>
  </a-menu-item>
</template>

<script setup lang="ts">
import type { MenuItem } from '@/api/user'

defineProps<{
  menu: MenuItem
  getIcon: (iconName?: string) => any
}>()
</script>
