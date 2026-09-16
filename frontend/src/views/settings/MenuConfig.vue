<template>
  <div class="menu-config-page">
    <div class="page-header">
      <BackButton to="/settings" text="返回设置" />
      <div class="header-text">
        <h1 class="page-title">工作区菜单配置</h1>
        <p class="page-desc">拖拽排序、切换显隐，为全员统一定义侧边栏业务操作流</p>
      </div>
    </div>

    <div class="config-body">
      <!-- 模块 Tab 切换 -->
      <el-tabs v-model="activeModule" class="module-tabs" @tab-change="onModuleChange">
        <el-tab-pane v-for="mod in modules" :key="mod.key" :label="mod.label" :name="mod.key" />
      </el-tabs>

      <div class="drag-area">
        <div class="drag-header">
          <span class="drag-header-title">{{ currentModuleLabel }} — 菜单项</span>
          <div class="drag-header-actions">
            <el-button text type="warning" @click="resetModule">
              <el-icon><RefreshLeft /></el-icon>恢复默认
            </el-button>
            <el-button type="primary" :loading="saving" @click="saveModule">
              <el-icon><Check /></el-icon>保存配置
            </el-button>
          </div>
        </div>

        <draggable
          v-model="editingItems"
          item-key="path"
          handle=".drag-handle"
          ghost-class="drag-ghost"
          animation="200"
          class="menu-list"
        >
          <template #item="{ element, index }">
            <div class="menu-item" :class="{ 'is-hidden': element.visible === false }">
              <div class="menu-item-main">
                <el-icon class="drag-handle"><Rank /></el-icon>
                <span class="item-label">{{ element.label }}</span>
                <span class="item-path">{{ element.path }}</span>
                <el-tooltip :content="element.visible === false ? '点击显示' : '点击隐藏'" placement="top">
                  <el-button
                    text
                    :type="element.visible === false ? 'info' : 'primary'"
                    class="visibility-btn"
                    @click="toggleVisible(index)"
                  >
                    <el-icon><component :is="element.visible === false ? Hide : View" /></el-icon>
                  </el-button>
                </el-tooltip>
              </div>

              <!-- 子菜单 -->
              <draggable
                v-if="element.children && element.children.length"
                v-model="element.children"
                item-key="path"
                handle=".drag-handle"
                ghost-class="drag-ghost"
                animation="200"
                class="sub-menu-list"
              >
                <template #item="{ element: child, index: ci }">
                  <div class="menu-item sub-item" :class="{ 'is-hidden': child.visible === false }">
                    <div class="menu-item-main">
                      <el-icon class="drag-handle"><Rank /></el-icon>
                      <span class="item-label">{{ child.label }}</span>
                      <span class="item-path">{{ child.path }}</span>
                      <el-tooltip :content="child.visible === false ? '点击显示' : '点击隐藏'" placement="top">
                        <el-button
                          text
                          :type="child.visible === false ? 'info' : 'primary'"
                          class="visibility-btn"
                          @click="toggleChildVisible(index, ci)"
                        >
                          <el-icon><component :is="child.visible === false ? Hide : View" /></el-icon>
                        </el-button>
                      </el-tooltip>
                    </div>
                  </div>
                </template>
              </draggable>
            </div>
          </template>
        </draggable>

        <el-empty v-if="!editingItems.length" description="暂无菜单项" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { RefreshLeft, Check, Rank, View, Hide } from '@element-plus/icons-vue'
import draggable from 'vuedraggable'
import BackButton from '@/components/BackButton.vue'
import { DEFAULT_MENU_CONFIG, useMenuStore } from '@/stores/menu'
import { getMenuConfig, updateMenuConfig, resetMenuConfig } from '@/api/settings'

const menuStore = useMenuStore()

const modules = [
  { key: 'project', label: '项目管理' },
  { key: 'api', label: 'API 测试' },
  { key: 'web', label: 'Web 测试' },
  { key: 'app', label: 'App 测试' },
  { key: 'perf', label: '性能测试' }
]

const activeModule = ref('project')
const editingItems = ref([])
const remoteConfig = ref({})
const saving = ref(false)

const currentModuleLabel = computed(() => {
  const mod = modules.find(m => m.key === activeModule.value)
  return mod ? mod.label : ''
})

function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj))
}

function stripNonSerializable(items) {
  return items.map(item => {
    const cleaned = { path: item.path, label: item.label, visible: item.visible !== false }
    if (item.iconName) cleaned.iconName = item.iconName
    if (item.children && item.children.length) {
      cleaned.children = stripNonSerializable(item.children)
    }
    return cleaned
  })
}

function loadModuleItems(module) {
  const remote = remoteConfig.value[module]
  if (remote && Array.isArray(remote) && remote.length > 0) {
    editingItems.value = deepClone(remote)
  } else {
    const defaults = DEFAULT_MENU_CONFIG[module]
    editingItems.value = defaults ? deepClone(stripNonSerializable(defaults.items)) : []
  }
}

function onModuleChange(module) {
  loadModuleItems(module)
}

function toggleVisible(index) {
  const item = editingItems.value[index]
  item.visible = item.visible === false ? true : false
}

function toggleChildVisible(parentIdx, childIdx) {
  const child = editingItems.value[parentIdx].children[childIdx]
  child.visible = child.visible === false ? true : false
}

async function saveModule() {
  saving.value = true
  try {
    const items = stripNonSerializable(editingItems.value)
    await updateMenuConfig(activeModule.value, items)
    remoteConfig.value[activeModule.value] = deepClone(items)
    await menuStore.fetchMenuConfig()
    ElMessage.success('菜单配置保存成功，已全局生效')
  } catch (e) {
    ElMessage.error('保存失败：' + (e.response?.data?.message || e.message))
  } finally {
    saving.value = false
  }
}

async function resetModule() {
  try {
    await ElMessageBox.confirm(
      `确定要将「${currentModuleLabel.value}」模块的菜单恢复为系统默认配置吗？`,
      '恢复默认',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }

  try {
    await resetMenuConfig(activeModule.value)
    delete remoteConfig.value[activeModule.value]
    loadModuleItems(activeModule.value)
    await menuStore.fetchMenuConfig()
    ElMessage.success('已恢复默认配置')
  } catch (e) {
    ElMessage.error('重置失败：' + (e.response?.data?.message || e.message))
  }
}

onMounted(async () => {
  try {
    const res = await getMenuConfig()
    const data = res.data?.data
    if (data && typeof data === 'object') {
      remoteConfig.value = data
    }
  } catch { /* ignore */ }
  loadModuleItems(activeModule.value)
})
</script>

<style scoped>
.menu-config-page {
  min-height: 100%;
  padding: 24px;
}

.page-header {
  margin-bottom: 28px;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.page-header :deep(.back-btn) {
  margin-bottom: 0;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--app-text-primary);
  margin: 0 0 4px 0;
}

.page-desc {
  font-size: 14px;
  color: var(--app-text-muted);
  margin: 0;
}

.config-body {
  background: var(--cockpit-card-bg, #fff);
  border: 1px solid var(--cockpit-card-border, #e4e7ed);
  border-radius: 12px;
  padding: 20px 24px 24px;
}

.module-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.drag-area {
  margin-top: 20px;
}

.drag-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.drag-header-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.drag-header-actions {
  display: flex;
  gap: 8px;
}

.menu-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.menu-item {
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 8px;
  background: var(--el-bg-color, #fff);
  transition: all 0.2s;
}

.menu-item:hover {
  border-color: var(--el-color-primary-light-5, #a0cfff);
}

.menu-item.is-hidden {
  opacity: 0.45;
}

.menu-item-main {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
}

.drag-handle {
  cursor: grab;
  color: var(--app-text-muted, #909399);
  font-size: 18px;
  flex-shrink: 0;
}

.drag-handle:active {
  cursor: grabbing;
}

.item-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--app-text-primary);
  white-space: nowrap;
}

.item-path {
  font-size: 12px;
  color: var(--app-text-muted, #909399);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.visibility-btn {
  flex-shrink: 0;
  font-size: 16px;
}

.sub-menu-list {
  padding: 0 14px 10px 42px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sub-item {
  background: var(--el-fill-color-lighter, #fafafa);
  border-color: var(--el-border-color-extra-light, #f2f6fc);
}

.sub-item .menu-item-main {
  padding: 8px 12px;
}

.drag-ghost {
  opacity: 0.4;
  background: var(--el-color-primary-light-9, #ecf5ff);
  border-color: var(--el-color-primary, #409eff);
  border-style: dashed;
}

@media (max-width: 700px) {
  .drag-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
}
</style>
