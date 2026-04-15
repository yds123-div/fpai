<template>
  <div class="table-section">
    <div class="section-title">{{ section.title }}</div>
    <p v-if="section.description" class="section-desc">{{ section.description }}</p>
    <div class="table-wrapper">
      <table class="compare-table">
        <thead>
          <tr>
            <th v-for="h in section.table.headers" :key="h" :class="{ highlight: isHighlight(h) }">
              {{ h }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in section.table.rows" :key="idx">
            <td
              v-for="h in section.table.headers"
              :key="h"
              :class="{ highlight: isHighlight(h) }"
            >
              {{ row[h] ?? '-' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TableSection } from '@/types/fundAnalysis'

const props = defineProps<{ section: TableSection }>()

const highlightSet = new Set(props.section.table.highlight || [])

function isHighlight(header: string): boolean {
  return highlightSet.has(header)
}
</script>

<style scoped>
.table-section {
  margin: 12px 0;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-primary, #1a1a1a);
}
.section-desc {
  font-size: 13px;
  color: var(--text-secondary, #888);
  margin-bottom: 8px;
}
.table-wrapper {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 400px;
}
.compare-table th {
  background: var(--table-header-bg, #fafafa);
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  white-space: nowrap;
  border-bottom: 2px solid var(--border-color, #e8e8e8);
  color: var(--text-primary, #333);
}
.compare-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-light, #f0f0f0);
  color: var(--text-primary, #333);
  white-space: pre-wrap;
  word-break: break-word;
}
.compare-table tbody tr:hover {
  background: var(--table-hover-bg, #f5f5f5);
}
.compare-table .highlight {
  background: var(--highlight-bg, #e6f7ff);
  font-weight: 500;
}
</style>
