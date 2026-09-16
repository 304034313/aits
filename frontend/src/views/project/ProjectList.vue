<template>
  <!-- 页面头部 -->
  <div class="page-header">
    <div class="header-content">
      <div class="header-left">
        <div class="header-icon">
          <el-icon>
            <Setting />
          </el-icon>
        </div>
        <div class="header-text">
          <h2>项目管理列表</h2>
          <p>管理不同项目的相关配置</p>
        </div>
      </div>
      <div class="header-actions">
        <el-button type="primary" icon="Plus" @click="showCreateDialog = true" class="create-btn">
          新建项目
        </el-button>
      </div>
    </div>
  </div>

  <!-- 项目列表 -->
  <el-card class="projects-card">
    <div class="card-header">
      <div class="card-header-left">
        <span>项目列表</span>
      </div>
      <div class="card-header-right">
        <el-input v-model="searchQuery" placeholder="搜索项目名称或描述..." prefix-icon="Search" style="width: 300px;" clearable
          @input="handleSearch" />
      </div>
    </div>

    <el-table :data="filteredProjects" style="width: 100%" v-loading="loading">
      <el-table-column prop="name" label="项目名称" min-width="200">
        <template #default="scope">
          <div class="project-name">
            <div class="project-icon-wrapper" :style="{ backgroundColor: getProjectIconColor(scope.row.name) }">
              <span class="project-icon-text">{{ getProjectIconText(scope.row.name) }}</span>
            </div>
            <div class="project-info">
              <div class="project-title">
                {{ scope.row.name }}
              </div>
              <div class="project-description">{{ scope.row.description || '暂无描述' }}</div>
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="created_at" label="创建时间" width="160">
        <template #default="scope">
          {{ formatDate(scope.row.created_at) }}
        </template>
      </el-table-column>

      <el-table-column prop="updated_at" label="最后更新" width="160">
        <template #default="scope">
          {{ formatDate(scope.row.updated_at) }}
        </template>
      </el-table-column>

      <el-table-column label="类型" width="112" align="center">
        <template #default="scope">
          <el-tag size="small" :type="projectTypeTagType(scope.row.project_type)">
            {{ projectTypeLabel(scope.row.project_type) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="280" fixed="right">
        <template #default="scope">
          <el-button type="success" size="small" @click="setAsCurrentProject(scope.row)"
            :disabled="isCurrentProject(scope.row.id)">
            {{ isCurrentProject(scope.row.id) ? '当前项目' : '设为当前项目' }}
          </el-button>
          <el-button type="warning" size="small" @click="editProject(scope.row)">
            编辑
          </el-button>
          <el-button type="danger" size="small" @click="deleteProject(scope.row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrapper">
      <el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize" :page-sizes="[10, 20, 50, 100]"
        :total="total" layout="total, sizes, prev, pager, next, jumper" @size-change="handleSizeChange"
        @current-change="handleCurrentChange" />
    </div>
  </el-card>

  <!-- 创建项目对话框 -->
  <el-dialog v-model="showCreateDialog" title="创建新项目" width="600px" :close-on-click-modal="false" @close="resetCreateForm">
    <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="100px">
      <el-form-item label="项目名称" prop="name">
        <el-input v-model="createForm.name" placeholder="请输入项目名称" />
      </el-form-item>

      <el-form-item label="项目描述" prop="description">
        <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="请输入项目描述" maxlength="500"
          show-word-limit />
      </el-form-item>

      <el-form-item label="项目类型" prop="project_type">
        <el-select
          v-model="createForm.project_type"
          placeholder="请选择项目类型"
          style="width: 100%"
          @change="onCreateProjectTypeChange"
        >
          <el-option
            v-for="opt in projectTypeOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item
        v-if="createForm.project_type === 'perf'"
        label="关联接口项目"
        prop="linked_api_project_ids"
      >
        <el-select
          v-model="createForm.linked_api_project_ids"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          placeholder="请选择要关联的接口自动化项目（可多选）"
          style="width: 100%"
          :loading="apiProjectsForLinkLoading"
        >
          <el-option
            v-for="p in apiProjectsForLink"
            :key="p.id"
            :label="p.name || `项目 #${p.id}`"
            :value="p.id"
          />
        </el-select>
        <div class="form-item-hint">性能项目可关联一个或多个接口自动化项目，用于压测场景中选择来源接口数据</div>
      </el-form-item>

      <el-form-item label="版本" prop="version">
        <el-input v-model="createForm.version" placeholder="请输入版本号" />
      </el-form-item>

      <el-form-item label="仓库地址">
        <el-input v-model="createForm.repository_url" placeholder="请输入Git仓库地址" />
      </el-form-item>

      <el-form-item label="文档地址">
        <el-input v-model="createForm.documentation_url" placeholder="请输入文档地址" />
      </el-form-item>
    </el-form>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="handleCancelCreate">取消</el-button>
        <el-button type="primary" @click="createProject" :loading="creating">
          创建
        </el-button>
      </span>
    </template>
  </el-dialog>

  <!-- 编辑项目对话框 -->
  <el-dialog v-model="showEditDialog" title="编辑项目" width="600px" :close-on-click-modal="false">
    <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="100px">
      <el-form-item label="项目名称" prop="name">
        <el-input v-model="editForm.name" placeholder="请输入项目名称" />
      </el-form-item>

      <el-form-item label="项目描述" prop="description">
        <el-input v-model="editForm.description" type="textarea" :rows="3" placeholder="请输入项目描述" maxlength="500"
          show-word-limit />
      </el-form-item>

      <el-form-item label="项目类型" prop="project_type">
        <el-select
          v-model="editForm.project_type"
          placeholder="请选择项目类型"
          style="width: 100%"
          @change="onEditProjectTypeChange"
        >
          <el-option
            v-for="opt in projectTypeOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item
        v-if="editForm.project_type === 'perf'"
        label="关联接口项目"
        prop="linked_api_project_ids"
      >
        <el-select
          v-model="editForm.linked_api_project_ids"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          placeholder="请选择要关联的接口自动化项目（可多选）"
          style="width: 100%"
          :loading="apiProjectsForLinkLoading"
        >
          <el-option
            v-for="p in apiProjectsForLink"
            :key="p.id"
            :label="p.name || `项目 #${p.id}`"
            :value="p.id"
          />
        </el-select>
        <div class="form-item-hint">保存后将写入性能项目与接口项目的关联关系</div>
      </el-form-item>

      <el-form-item label="版本" prop="version">
        <el-input v-model="editForm.version" placeholder="请输入版本号" />
      </el-form-item>


      <el-form-item label="仓库地址">
        <el-input v-model="editForm.repository_url" placeholder="请输入Git仓库地址" />
      </el-form-item>

      <el-form-item label="文档地址">
        <el-input v-model="editForm.documentation_url" placeholder="请输入文档地址" />
      </el-form-item>
    </el-form>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="updateProject" :loading="updating">
          保存
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import {
  getProjects,
  getProject,
  createProject as createProjectAPI,
  updateProject as updateProjectAPI,
  deleteProject as deleteProjectAPI
} from '@/api/projects'
import { useProjectStore } from '@/stores/project'

const router = useRouter()
const projectStore = useProjectStore()

// 响应式数据
const loading = ref(false)
const creating = ref(false)
const updating = ref(false)
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const projects = ref([])

const projectTypeOptions = [
  { value: 'api', label: '接口自动化' },
  { value: 'web', label: 'Web 测试' },
  { value: 'app', label: 'App 测试' },
  { value: 'perf', label: '性能测试' }
]

/** 供性能项目多选关联：全部接口自动化项目 */
const apiProjectsForLink = ref([])
const apiProjectsForLinkLoading = ref(false)

// 表单数据
const createForm = reactive({
  name: '',
  description: '',
  project_type: 'api',
  linked_api_project_ids: [],
  version: '',
  repository_url: '',
  documentation_url: ''
})

const editForm = reactive({
  id: null,
  name: '',
  description: '',
  project_type: 'api',
  linked_api_project_ids: [],
  version: '',
  repository_url: '',
  documentation_url: ''
})

// 表单验证规则
const createRules = {
  name: [
    { required: true, message: '请输入项目名称', trigger: 'blur' },
    { min: 2, max: 50, message: '项目名称长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  description: [
    { max: 500, message: '项目描述不能超过500个字符', trigger: 'blur' }
  ]
}

const editRules = {
  name: [
    { required: true, message: '请输入项目名称', trigger: 'blur' },
    { min: 2, max: 50, message: '项目名称长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  description: [
    { max: 500, message: '项目描述不能超过500个字符', trigger: 'blur' }
  ]
}

// 表单引用
const createFormRef = ref(null)
const editFormRef = ref(null)

// 计算属性
const filteredProjects = computed(() => {
  if (!searchQuery.value) return projects.value

  return projects.value.filter(project =>
    project.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
    (project.description && project.description.toLowerCase().includes(searchQuery.value.toLowerCase()))
  )
})

// 当前项目（从store获取）
const currentProject = computed(() => projectStore.currentProject)

// 格式化日期
const formatDate = (date) => {
  return dayjs(date).format('YYYY-MM-DD HH:mm')
}

function projectTypeLabel(type) {
  const hit = projectTypeOptions.find((o) => o.value === type)
  return hit ? hit.label : type || '—'
}

function projectTypeTagType(type) {
  if (type === 'perf') return 'danger'
  if (type === 'api') return 'primary'
  if (type === 'web') return 'success'
  if (type === 'app') return 'warning'
  return 'info'
}

function onCreateProjectTypeChange() {
  if (createForm.project_type !== 'perf') {
    createForm.linked_api_project_ids = []
  }
}

function onEditProjectTypeChange() {
  if (editForm.project_type !== 'perf') {
    editForm.linked_api_project_ids = []
  }
}

function normalizeProjectsPayloadItems(res) {
  let items = []
  if (res?.success && res?.data) {
    items = res.data.items || (Array.isArray(res.data) ? res.data : [])
  } else if (Array.isArray(res)) {
    items = res
  }
  return items
}

async function loadApiProjectsForLink() {
  apiProjectsForLinkLoading.value = true
  try {
    const pageSize = 100
    const merged = []
    let page = 1
    let total = 0
    for (;;) {
      const res = await getProjects({ project_type: 'api', page, page_size: pageSize })
      const items = normalizeProjectsPayloadItems(res)
      total = res?.data?.pagination?.total ?? total
      merged.push(...items)
      if (items.length < pageSize) break
      if (total > 0 && merged.length >= total) break
      page += 1
      if (page > 50) break
    }
    const seen = new Set()
    apiProjectsForLink.value = merged.filter((p) => {
      if (!p?.id || seen.has(p.id)) return false
      seen.add(p.id)
      return true
    })
  } catch {
    apiProjectsForLink.value = []
    ElMessage.error('加载接口自动化项目列表失败')
  } finally {
    apiProjectsForLinkLoading.value = false
  }
}

// 处理搜索
const handleSearch = () => {
  currentPage.value = 1
  loadProjects()
}

// 编辑项目（拉详情保证关联接口回显完整）
const editProject = async (project) => {
  try {
    const raw = await getProject(project.id)
    const d = raw?.success && raw.data != null ? raw.data : raw?.data ?? raw
    const detail = d && d.id != null ? d : project

    let linkedIds = []
    if (Array.isArray(detail.linked_api_projects) && detail.linked_api_projects.length) {
      linkedIds = detail.linked_api_projects.map((id) => Number(id))
    } else if (Array.isArray(detail.linked_api_project_details) && detail.linked_api_project_details.length) {
      linkedIds = detail.linked_api_project_details.map((x) => Number(x.id))
    }

    Object.assign(editForm, {
      id: detail.id,
      name: detail.name,
      description: detail.description || '',
      project_type: detail.project_type || 'api',
      linked_api_project_ids: linkedIds,
      version: detail.version,
      repository_url: detail.repository_url || '',
      documentation_url: detail.documentation_url || ''
    })
    await loadApiProjectsForLink()
    showEditDialog.value = true
  } catch {
    ElMessage.error('加载项目详情失败')
  }
}

// 删除项目
const deleteProject = async (project) => {
  try {
    await ElMessageBox.confirm(
      `确认删除项目 "${project.name}" 吗？该操作不可恢复，项目下所有测试数据将被清空。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // 调用删除API
    await deleteProjectAPI(project.id)
    ElMessage.success('项目删除成功')
    await loadProjects()
  } catch (error) {
    if (error.response?.data?.message) {
      ElMessage.error(error.response.data.message)
    } else if (error.message) {
      ElMessage.error(error.message)
    } else {
      // 用户取消
    }
  }
}

// 重置创建表单
const resetCreateForm = () => {
  Object.assign(createForm, {
    name: '',
    description: '',
    project_type: 'api',
    linked_api_project_ids: [],
    version: '',
    repository_url: '',
    documentation_url: ''
  })
  // 清除表单验证状态
  if (createFormRef.value) {
    createFormRef.value.clearValidate()
  }
}

// 取消创建
const handleCancelCreate = () => {
  showCreateDialog.value = false
  // 对话框关闭时会触发 @close 事件，自动调用 resetCreateForm
}

// 创建项目
const createProject = async () => {
  try {
    await createFormRef.value.validate()
    creating.value = true

    const createPayload = {
      name: createForm.name.trim(),
      description: (createForm.description || '').trim(),
      project_type: createForm.project_type || 'api'
    }
    if (createForm.project_type === 'perf') {
      createPayload.linked_api_projects = [...(createForm.linked_api_project_ids || [])]
    }

    await createProjectAPI(createPayload)
    ElMessage.success('项目创建成功')

    // 重置表单
    resetCreateForm()

    showCreateDialog.value = false
    await loadProjects()
  } catch (error) {
    if (error.response?.data?.message) {
      ElMessage.error(error.response.data.message)
    } else if (error.message) {
      ElMessage.error(error.message)
    } else {
      ElMessage.error('创建失败，请检查输入信息')
    }
  } finally {
    creating.value = false
  }
}

// 更新项目
const updateProject = async () => {
  try {
    await editFormRef.value.validate()
    updating.value = true

    const patchPayload = {
      name: editForm.name.trim(),
      description: (editForm.description || '').trim(),
      project_type: editForm.project_type || 'api',
      linked_api_projects:
        editForm.project_type === 'perf' ? [...(editForm.linked_api_project_ids || [])] : []
    }

    await updateProjectAPI(editForm.id, patchPayload)
    ElMessage.success('项目更新成功')

    showEditDialog.value = false
    await loadProjects()
  } catch (error) {
    if (error.response?.data?.message) {
      ElMessage.error(error.response.data.message)
    } else if (error.message) {
      ElMessage.error(error.message)
    } else {
      ElMessage.error('更新失败，请检查输入信息')
    }
  } finally {
    updating.value = false
  }
}

// 分页处理
const handleSizeChange = (val) => {
  pageSize.value = val
  currentPage.value = 1
  loadProjects()
}

const handleCurrentChange = (val) => {
  currentPage.value = val
  loadProjects()
}

// 加载项目列表
const loadProjects = async () => {
  loading.value = true
  try {
    const response = await getProjects({
      page: currentPage.value,
      page_size: pageSize.value,
      search: searchQuery.value
    })

    // 处理统一响应格式
    if (response && response.success && response.data) {
      if (response.data.items) {
        // 分页响应
        projects.value = response.data.items
        total.value = response.data.pagination ? response.data.pagination.total : response.data.total || 0
      } else {
        // 普通列表响应
        projects.value = response.data
        total.value = Array.isArray(response.data) ? response.data.length : 0
      }
    } else {
      // 兼容直接数组格式
      projects.value = response
      total.value = Array.isArray(response) ? response.length : 0
    }
  } catch (error) {
    ElMessage.error('加载项目列表失败')
  } finally {
    loading.value = false
  }
}

// 设置为当前项目
const setAsCurrentProject = async (project) => {
  try {
    await ElMessageBox.confirm(
      `确认将项目 "${project.name}" 设为当前项目吗？`,
      '确认设为当前项目',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    projectStore.setCurrentProjectById(project.id)
    ElMessage.success('项目已设为当前项目')
  } catch (error) {
    // 用户取消操作，不需要显示错误
  }
}


// 判断是否为当前项目
const isCurrentProject = (projectId) => {
  return currentProject.value?.id === projectId
}

// 图标工具函数
const getProjectIconText = (name) => {
  return name ? name.charAt(0).toUpperCase() : 'P'
}

const getProjectIconColor = (name) => {
  if (!name) return '#409EFF'
  
  const firstChar = name.charAt(0).toLowerCase()
  const colors = {
    'a': '#FF6B6B', 'b': '#4ECDC4', 'c': '#45B7D1', 'd': '#96CEB4', 'e': '#FFEAA7',
    'f': '#DDA0DD', 'g': '#98D8C8', 'h': '#F7DC6F', 'i': '#BB8FCE', 'j': '#85C1E9',
    'k': '#F8C471', 'l': '#82E0AA', 'm': '#F1948A', 'n': '#85C1E9', 'o': '#F7DC6F',
    'p': '#D7BDE2', 'q': '#A9DFBF', 'r': '#F9E79F', 's': '#AED6F1', 't': '#A3E4D7',
    'u': '#D5DBDB', 'v': '#FADBD8', 'w': '#D1F2EB', 'x': '#E8DAEF', 'y': '#FCF3CF',
    'z': '#D6EAF8'
  }
  
  return colors[firstChar] || '#409EFF'
}

// 初始化
watch(showCreateDialog, (open) => {
  if (open) loadApiProjectsForLink()
})

onMounted(async () => {
  await loadProjects()
  await loadApiProjectsForLink()
})
</script>

<style scoped>
.projects-page {
  padding: 20px;
}


/* 页面头部样式 */
.page-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16px 16px 0 0;
  padding: 20px 32px;
  margin-bottom: 0;
  color: white;
  box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
  position: relative;
  overflow: hidden;
}

.page-header::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  /* background: linear-gradient(45deg, rgba(255, 255, 255, 0.1) 0%, transparent 100%); */
  pointer-events: none;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: relative;
  z-index: 1;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-icon {
  width: 40px;
  height: 40px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(10px);
}

.header-icon .el-icon {
  font-size: 24px;
  color: white;
}

.header-text h2 {
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 2px 0;
  color: white;
  line-height: 1.2;
}

.header-text p {
  font-size: 13px;
  margin: 0;
  opacity: 0.9;
  color: white;
  line-height: 1.2;
}

.create-btn {
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: white;
  backdrop-filter: blur(10px);
  font-weight: 500;
  padding: 12px 24px;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.create-btn:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.header-actions {
  display: flex;
  gap: 10px;
}



.projects-card {
  margin-bottom: 20px;
  border-radius: 0 0 16px 16px;
  border-top: none;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header-left {
  display: flex;
  align-items: center;
}

.card-header-left span {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}


.project-name {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.project-icon-wrapper {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.project-icon-wrapper:hover {
  transform: scale(1.05);
}

.project-icon-text {
  color: white;
  font-weight: bold;
  font-size: 16px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
  user-select: none;
}

.project-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.project-title {
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.2;
  display: flex;
  align-items: center;
}

.project-description {
  font-size: 12px;
  color: #909399;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}


.pagination-wrapper {
  margin-top: 20px;
  text-align: right;
}

.dialog-footer {
  text-align: right;
}

.form-item-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 15px;
  }

  .header-actions {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 15px;
  }

  .project-name {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .project-icon-wrapper {
    width: 32px;
    height: 32px;
  }
}
</style>
