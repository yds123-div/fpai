<template>
  <div class="products-view">
    <a-typography-title :level="4">产品列表 / 筛选</a-typography-title>
    <a-card size="small" style="margin-bottom: 16px">
      <a-form layout="inline" @finish="onSearch">
        <a-form-item label="产品代码" name="productCode">
          <a-input v-model:value="productCode" placeholder="支持模糊" style="width: 140px" allow-clear />
        </a-form-item>
        <a-form-item label="产品名称" name="keyword">
          <a-input v-model:value="keyword" placeholder="支持模糊" style="width: 180px" allow-clear />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" :loading="loading" @click="onSearch">搜索</a-button>
        </a-form-item>
        <a-form-item>
          <a-button :loading="syncLoading" @click="onSync">同步基金数据</a-button>
        </a-form-item>
      </a-form>
    </a-card>
    <a-alert v-if="errorMsg" type="error" :message="errorMsg" show-icon style="margin-bottom: 16px" />
    <a-table
      :columns="columns"
      :data-source="products"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      size="small"
      @change="onTableChange"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { getProductsSearch, syncFundProducts } from '@/api/products'

const productCode = ref('')
const keyword = ref('')
const loading = ref(false)
const syncLoading = ref(false)
const errorMsg = ref('')
const products = ref([])
const total = ref(0)

const columns = [
  { title: '产品代码', dataIndex: 'id', key: 'id', width: 100, ellipsis: true },
  { title: '产品名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '类型', dataIndex: 'productType', key: 'productType', width: 100 },
  { title: '风险等级', dataIndex: 'riskLevel', key: 'riskLevel', width: 90 },
  { title: '期限', dataIndex: 'term', key: 'term', width: 80 },
]

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
  showSizeChanger: true,
  showTotal: (t) => `共 ${t} 条`,
})

async function loadProducts() {
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await getProductsSearch({
      productCode: productCode.value?.trim() || undefined,
      keyword: keyword.value?.trim() || undefined,
      page: pagination.current,
      pageSize: pagination.pageSize,
    })
    products.value = data.products || []
    total.value = data.total ?? 0
    pagination.total = total.value
  } catch (e) {
    errorMsg.value = e?.message || '产品列表获取失败'
    products.value = []
  } finally {
    loading.value = false
  }
}

async function onSync() {
  syncLoading.value = true
  try {
    const data = await syncFundProducts({ limit: 100 })
    message.success(`同步完成：有效${data.valid ?? 0}条，写入${data.affected ?? 0}条`)
    pagination.current = 1
    await loadProducts()
  } catch (e) {
    message.error(e?.message || '同步失败')
  } finally {
    syncLoading.value = false
  }
}

function onSearch() {
  pagination.current = 1
  loadProducts()
}

function onTableChange(pag) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize || 10
  loadProducts()
}

onMounted(() => loadProducts())
</script>

<style scoped>
.products-view {
  margin: 32px;
  padding: 32px;
}
</style>
