<template>
  <div v-if="showBar" class="sonic-workspace-bar">
    <div class="sonic-workspace-bar__inner">
      <span class="sonic-workspace-bar__label">Sonic</span>
      <el-tag :type="hasToken ? 'success' : 'warning'" size="small" effect="plain">
        {{ hasToken ? '已登录' : '未登录' }}
      </el-tag>
      <span v-if="sonicProjectHint && !showSonicProjectSelect" class="sonic-workspace-bar__hint">{{ sonicProjectHint }}</span>
      <template v-if="showSonicProjectSelect">
        <span class="sonic-workspace-bar__hint-label">绑定 Sonic 项目</span>
        <el-select
          :model-value="projectStore.currentProject?.sonic_project_id ?? undefined"
          placeholder="选择 Sonic 项目"
          filterable
          clearable
          :loading="loadingSonicProjects"
          style="width: min(320px, 40vw)"
          @visible-change="(v) => v && fetchSonicProjects()"
          @update:model-value="onSonicProjectChange"
        >
          <el-option
            v-for="p in sonicProjectList"
            :key="p.id"
            :label="sonicProjectOptionLabel(p)"
            :value="p.id"
          />
        </el-select>
        <span v-if="sonicProjectHint" class="sonic-workspace-bar__hint">{{ sonicProjectHint }}</span>
      </template>
      <div class="sonic-workspace-bar__actions">
        <el-button v-if="!hasToken" size="small" type="primary" @click="dialogVisible = true">
          绑定 Sonic 账号
        </el-button>
        <el-button v-else size="small" @click="onLogout">退出 Sonic</el-button>
      </div>
    </div>

    <el-dialog
      v-model="dialogVisible"
      title="Sonic 账号登录"
      width="420px"
      destroy-on-close
      :close-on-click-modal="false"
      @closed="resetForm"
    >
      <p class="sonic-login-tip">
        App 测试设备、用例、执行记录由 Sonic 平台提供，需使用 Sonic 控制台中的用户名与密码登录。
      </p>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="88px" @submit.prevent>
        <el-form-item label="用户名" prop="userName">
          <el-input v-model="form.userName" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">登录</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import sonicHttp, { getSonicToken, clearSonicToken, sonicLogin, ensureSonicSession } from '@/api/sonicHttp'
import { patchProject } from '@/api/projects'

const route = useRoute()
const projectStore = useProjectStore()

const showBar = computed(() => route.path.startsWith('/app-testing'))
const hasToken = ref(false)
const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const form = ref({ userName: '', password: '' })
const rules = {
  userName: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const showSonicProjectSelect = computed(() => {
  const p = projectStore.currentProject
  return Boolean(showBar.value && p && p.project_type === 'app' && hasToken.value)
})

const sonicProjectHint = computed(() => {
  const p = projectStore.currentProject
  if (!p || p.project_type !== 'app') return ''
  const sid = p.sonic_project_id
  if (sid == null || sid === '') {
    return '未配置 Sonic 项目，请在下拉框中选择'
  }
  return `已绑定 Sonic 项目 #${sid}`
})

const sonicProjectList = ref([])
const loadingSonicProjects = ref(false)

function sonicPlatformLabel(raw) {
  const s = String(raw || 'android').trim().toLowerCase()
  return s === 'ios' ? 'iOS' : 'Android'
}

function sonicProjectOptionLabel(p) {
  const name = p.projectName || p.name || '项目'
  const plat = sonicPlatformLabel(p.platform)
  return `${name} (#${p.id}) · ${plat}`
}

async function fetchSonicProjects() {
  if (!getSonicToken()) {
    const ok = await ensureSonicSession({ silent: true })
    if (!ok) {
      sonicProjectList.value = []
      return
    }
  }
  loadingSonicProjects.value = true
  try {
    const res = await sonicHttp.get('/controller/projects/list')
    const rows = res?.data
    sonicProjectList.value = Array.isArray(rows) ? rows : []
  } catch {
    sonicProjectList.value = []
  } finally {
    loadingSonicProjects.value = false
  }
}

async function onSonicProjectChange(sid) {
  const p = projectStore.currentProject
  if (!p?.id) return
  try {
    const raw = await patchProject(p.id, { sonic_project_id: sid ?? null })
    if (!raw?.success) {
      ElMessage.error(raw?.message || '保存失败')
      return
    }
    const updated = raw.data && typeof raw.data === 'object' ? raw.data : {}
    await projectStore.setCurrentProject({
      ...p,
      ...updated,
      sonic_project_id: sid ?? null
    })
    ElMessage.success('Sonic 项目绑定已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '保存失败')
  }
}

function syncToken() {
  hasToken.value = Boolean(getSonicToken())
}

function onLogout() {
  clearSonicToken()
  syncToken()
  ElMessage.success('已退出 Sonic')
}

function resetForm() {
  form.value = { userName: '', password: '' }
}

async function onSubmit() {
  const f = formRef.value
  if (!f) return
  try {
    await f.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    await sonicLogin({ userName: form.value.userName, password: form.value.password })
    ElMessage.success('Sonic 登录成功')
    syncToken()
    await fetchSonicProjects()
    dialogVisible.value = false
    resetForm()
  } catch (e) {
    /* sonicHttp 已提示 */
  } finally {
    submitting.value = false
  }
}

function onSonicAuthExpired() {
  syncToken()
}

onMounted(() => {
  syncToken()
  window.addEventListener('aits-sonic-auth-expired', onSonicAuthExpired)
  window.addEventListener('storage', syncToken)
})

onBeforeUnmount(() => {
  window.removeEventListener('aits-sonic-auth-expired', onSonicAuthExpired)
  window.removeEventListener('storage', syncToken)
})

watch(showBar, (v) => {
  if (v) {
    ensureSonicSession({ silent: true }).finally(() => {
      syncToken()
    })
  }
})
</script>

<style scoped>
.sonic-workspace-bar {
  flex-shrink: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-light);
}
.sonic-workspace-bar__inner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  flex-wrap: wrap;
}
.sonic-workspace-bar__label {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.sonic-workspace-bar__hint {
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.sonic-workspace-bar__hint-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.sonic-workspace-bar__actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}
.sonic-login-tip {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
</style>
