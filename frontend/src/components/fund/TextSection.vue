<template>
  <div class="text-section">
    <div class="section-title">{{ section.title }}</div>
    <div v-if="section.tags?.length" class="section-tags">
      <span v-for="tag in section.tags" :key="tag" class="tag" :class="tagClass(tag)">
        <span class="tag-icon" aria-hidden="true">{{ tagIcon(tag) }}</span>
        <span>{{ tag }}</span>
      </span>
    </div>
    <div class="section-content" style="white-space: pre-wrap">{{ section.content }}</div>
  </div>
</template>

<script setup lang="ts">
import type { TextSection } from '@/types/fundAnalysis'

defineProps<{ section: TextSection }>()

function isRiskTag(tag: string): boolean {
  return /风险|risk/i.test(tag)
}

function isExpertTag(tag: string): boolean {
  return /专家|观点|expert|opinion/i.test(tag)
}

function tagClass(tag: string): string {
  if (isRiskTag(tag)) return 'tag-risk'
  if (isExpertTag(tag)) return 'tag-expert'
  return 'tag-default'
}

function tagIcon(tag: string): string {
  if (isRiskTag(tag)) return '!'
  if (isExpertTag(tag)) return 'i'
  return '•'
}
</script>

<style scoped>
.text-section {
  margin: 12px 0;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-primary, #1a1a1a);
}

.section-tags {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.tag-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
}

.tag-risk {
  background: #fff1f0;
  color: #cf1322;
  border: 1px solid #ffa39e;
}

.tag-risk .tag-icon {
  background: #cf1322;
  color: #fff;
}

.tag-expert {
  background: #e6f7ff;
  color: #096dd9;
  border: 1px solid #91d5ff;
}

.tag-expert .tag-icon {
  background: #096dd9;
  color: #fff;
}

.tag-default {
  background: #f6ffed;
  color: #389e0d;
  border: 1px solid #b7eb8f;
}

.tag-default .tag-icon {
  background: #389e0d;
  color: #fff;
}

.section-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary, #333);
}
</style>
