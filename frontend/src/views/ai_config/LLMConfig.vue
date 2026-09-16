<template>
  <div class="llm-config-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <BackButton to="/ai-config" />
      <div class="header-content">
        <div class="header-left">
          <div class="header-icon">
            <el-icon>
              <Connection />
            </el-icon>
          </div>
          <div class="header-text">
            <h2>LLM模型配置</h2>
            <p>管理 LLM 大模型与视觉模型；两类默认互不覆盖（LLM 默认用于文本生成，视觉默认用于 Web 截图断言）</p>
          </div>
        </div>
        <div class="header-actions">
          <el-button type="primary" icon="Plus" @click="addModelConfiguration" class="add-config-btn">
            添加AI模型配置
          </el-button>
        </div>
      </div>
    </div>

    <el-alert
      class="dual-default-alert"
      type="info"
      :closable="false"
      show-icon
      title="双默认说明"
    >
      <template #default>
        <span>
          系统支持 <strong>LLM 默认</strong>（用例生成、API 测试等）与 <strong>视觉默认</strong>（Web 自动化视觉断言）各自独立；
          点击「设为默认」时<strong>只影响同类型</strong>，不会替换另一类型的默认配置。
        </span>
      </template>
    </el-alert>

    <!-- 配置注意事项：折叠提示区块 -->
    <div class="config-tips-wrapper">
      <el-collapse v-model="configTipsActiveNames" accordion>
        <el-collapse-item name="tips">
          <template #title>
            <div class="config-tips-header">
              <div class="tips-title-row">
                <span class="tips-icon">💡</span>
                <span class="tips-title">常见配置问题指南</span>
                <span class="tips-arrow">
                  <el-icon>
                    <ArrowDown v-if="!configTipsActiveNames.includes('tips')" />
                    <ArrowUp v-else />
                  </el-icon>
                </span>
              </div>
              <span class="tips-subtitle">点击此处展开 / 收起，查看本地模型与云端模型在网络、路径和资源占用上的常见问题与解决建议。</span>
            </div>
          </template>

          <div class="config-tips-body">
            <div class="tips-section">
              <div class="tips-section-title">🔀 LLM 默认 vs 视觉默认</div>
              <ul class="tips-list">
                <li>
                  <span class="tips-label">互不覆盖：</span>
                  同一张配置表中可各有一条默认：<code>model_type=llm</code> 的 <strong>LLM 默认</strong>（如 DeepSeek）与
                  <code>model_type=vision</code> 的 <strong>视觉默认</strong>（如 qwen-vl-max、gpt-4o）。
                </li>
                <li>
                  <span class="tips-label">Web 视觉断言：</span>
                  用例中的「视觉/语义断言」只读取<strong>视觉模型</strong>配置，与 LLM 默认无关；未配置视觉模型时断言会失败。
                </li>
                <li>
                  <span class="tips-label">配置后生效：</span>
                  新增或修改视觉默认后，请<strong>重启 Celery Worker</strong>，再执行 Web 自动化用例。
                </li>
              </ul>
            </div>

            <div class="tips-section">
              <div class="tips-section-title">💻 本地模型部署（如 Ollama）</div>
              <ul class="tips-list">
                <li>
                  <span class="tips-label">量力而行（硬件限制）：</span>
                  强烈建议根据本机显存/内存选择参数量，<strong>16G 显存</strong>推荐使用 <strong>7B</strong> 或 <strong>14B</strong> 模型（如
                  <code>qwen2.5-coder:14b</code>）。强行加载过大模型（如 <strong>32B / 72B</strong>）会导致极度卡顿甚至内存溢出。
                </li>
                <li>
                  <span class="tips-label">提前拉取（前置准备）：</span>
                  在系统配置前，请务必先在本地终端执行
                  <code>ollama run &lt;模型名称&gt;</code>
                  ，确保模型文件已完整下载并在后台唤醒。
                </li>
                <li>
                  <span class="tips-label">网络与跨域（经典坑）：</span>
                  如果 AITS 服务端与 Ollama 不在同一台机器，或者使用 IP 地址访问，必须在运行 Ollama 的机器上配置环境变量
                  <code>OLLAMA_HOST=0.0.0.0</code>
                  和
                  <code>OLLAMA_ORIGINS=*</code>
                  ，并彻底重启系统或服务后方可生效。
                </li>
                <li>
                  <span class="tips-label">拼写检查：</span>
                  请确保【<strong>API 地址</strong>】无误（通常为
                  <code>http://localhost:11434</code>
                  或本机 IP），且【<strong>模型名称</strong>】与本地通过
                  <code>ollama list</code>
                  查看到的名称完全一致（包括后缀，如
                  <code>:14b</code>）。
                </li>
              </ul>
            </div>

            <div class="tips-section">
              <div class="tips-section-title">☁️ 云端模型接入（如 DeepSeek、OpenAI 等）</div>
              <ul class="tips-list">
                <li>
                  <span class="tips-label">参数核对：</span>
                  务必仔细核对【<strong>模型名称</strong>】、【<strong>API Key</strong>】和【<strong>API 地址</strong>】。
                  特别注意：大多数兼容 OpenAI 格式的 API 地址，必须以
                  <code>/v1</code>
                  结尾（例如
                  <code>https://api.deepseek.com/v1</code>
                  ）。
                </li>
                <li>
                  <span class="tips-label">额度与计费：</span>
                  如果连接测试一直提示 <code>402</code> 或 <code>403</code> 错误，请优先前往云服务商控制台，检查账户余额是否充足或 API 额度是否已耗尽。
                </li>
                <li>
                  <span class="tips-label">网络连通性：</span>
                  部分海外大模型 API（如 <strong>OpenAI</strong>、<strong>Claude</strong>）可能存在网络访问限制。如遇连接超时，请确保服务器具备访问外部网络的条件（或根据需要配置代理）。
                </li>
              </ul>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- LLM配置列表 -->
    <el-card class="config-list-card">
      <div class="card-header">
        <div class="card-header-left">
          <div class="card-title">
            配置列表
          </div>
        </div>
        <div class="card-header-right">
          <el-input v-model="searchQuery" placeholder="搜索模型配置..." prefix-icon="Search"
            style="width: 300px; margin-right: 10px;" clearable />
          <el-select v-model="modelTypeFilter" placeholder="模型类型" clearable style="width: 120px; margin-right: 10px;">
            <el-option label="LLM" value="llm" />
            <el-option label="视觉模型" value="vision" />
          </el-select>
        </div>
      </div>

      <el-alert
        v-if="!hasVisionConfiguration"
        class="vision-empty-hint"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #default>
          <span>
            尚未配置<strong>视觉模型</strong>。Web 自动化中的「视觉断言」将无法调用大模型（会提示未配置 API）。
          </span>
          <el-button type="primary" link class="vision-add-link" @click="addVisionModelConfiguration">
            添加视觉模型配置
          </el-button>
        </template>
      </el-alert>

      <el-table :data="filteredConfigurations" v-loading="loading" style="width: 100%">
        <el-table-column prop="model_name" label="配置信息" min-width="200">
          <template #default="scope">
            <div class="config-name">
              <div class="config-icon-wrapper model-icon-wrapper" :style="{ backgroundColor: getModelIconColor(scope.row.model_name) }">
                <span class="model-icon-text">{{ getModelIconText(scope.row.model_name) }}</span>
              </div>
              <div class="config-info">
                <div class="config-title">
                  {{ scope.row.model_name }}
                </div>
                <div class="config-model">{{ scope.row.model_name }}</div>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="model_type_display" label="模型类型" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.model_type === 'llm' ? 'primary' : 'success'" size="small">
              {{ scope.row.model_type_display }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="100" align="center">
          <template #default="scope">
            <el-switch
              :model-value="scope.row.is_active"
              @update:model-value="toggleModelStatus(scope.row)"
              :loading="scope.row.statusLoading"
            />
          </template>
        </el-table-column>

        <!-- 部署模式：与表单 infer 规则一致；本地 success(绿)、云端 primary(蓝) -->
        <el-table-column label="部署模式" width="110" align="center">
          <template #default="scope">
            <el-tag
              :type="getDeployModeTagType(scope.row)"
              size="small"
              effect="light"
              class="deploy-mode-table-tag"
            >
              {{ getDeployModeLabel(scope.row) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="base_url" label="API地址" min-width="200" show-overflow-tooltip />
        
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="400" fixed="right">
          <template #default="scope">
            <div class="table-actions">
              <el-link
                type="primary"
                :underline="false"
                class="set-default-link"
                :disabled="scope.row.is_default || settingDefaultId === scope.row.id"
                @click="setAsDefaultHandler(scope.row)"
              >
                {{ getDefaultActionText(scope.row) }}
              </el-link>
              <el-button type="primary" size="small" @click="testConnectionHandler(scope.row)"
                :loading="testingConnection === scope.row.id" :disabled="!scope.row.is_active"
                :title="scope.row.is_active ? '测试连接' : '请先启用配置'">
                测试连接
              </el-button>
              <el-button type="warning" size="small" @click="editConfiguration(scope.row)">
                编辑
              </el-button>
              <el-button type="danger" size="small" @click="handleDeleteModelConfiguration(scope.row)">
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>


    <!-- 创建/编辑AI模型配置对话框 -->
    <el-dialog v-model="showCreateModelDialog" :title="editingModelConfig ? '编辑AI模型配置' : '添加AI模型配置'" width="600px"
      :close-on-click-modal="false">
      <el-form ref="modelConfigFormRef" :model="modelConfigForm" :rules="modelConfigRules" label-width="120px">
        <el-form-item label="模型类型" prop="model_type">
          <el-select v-model="modelConfigForm.model_type" placeholder="选择模型类型" @change="onModelTypeChange"
            style="width: 100%">
            <el-option label="LLM大模型" value="llm" />
            <el-option label="视觉模型" value="vision" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="模型提供商" prop="provider">
          <el-select v-model="modelConfigForm.provider" placeholder="选择模型提供商" style="width: 100%">
            <el-option label="OpenAI" value="openai" />
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="Ollama" value="ollama" />
            <el-option label="通义千问" value="qwen" />
            <el-option label="文心一言" value="ernie" />
            <el-option label="智谱AI" value="zhipu" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>

        <!-- 部署模式：0=云端 API，1=本地私有化（如 Ollama）；与 base_url / api_key 校验联动 -->
        <el-form-item label="部署模式">
          <el-radio-group v-model="modelConfigForm.deploy_mode" class="deploy-mode-radio">
            <el-radio-button :label="0">云端模式</el-radio-button>
            <el-radio-button :label="1">本地私有化</el-radio-button>
          </el-radio-group>
          <div class="form-tip deploy-mode-tip">
            <el-text type="info" size="small">
              云端走公网供应商 API；本地私有化一般对接本机或内网推理服务（默认填充 Ollama OpenAI 兼容地址）。
            </el-text>
          </div>
        </el-form-item>
        
         <el-form-item label="API密钥" prop="api_key">
           <el-input 
             v-model="modelConfigForm.api_key" 
             type="password" 
             placeholder="请输入API密钥" 
             show-password 
             :disabled="modelConfigForm.provider === 'ollama' || modelConfigForm.deploy_mode === 1"
           />
           <div class="form-tip" v-if="modelConfigForm.provider === 'ollama' || modelConfigForm.deploy_mode === 1">
             <el-text type="info" size="small">
               {{ modelConfigForm.deploy_mode === 1 ? 'ℹ️ 本地私有化部署通常无需 API 密钥' : 'ℹ️ Ollama本地部署，无需API密钥' }}
             </el-text>
           </div>
         </el-form-item>
        
        <el-form-item label="API地址" prop="base_url">
          <el-input
            v-model="modelConfigForm.base_url"
            placeholder="请输入API地址（OpenAI 兼容 Base URL，如 https://api.xxx.com/v1）"
            class="base-url-input"
          >
            <template #append>
              <el-button
                @click="testConnectionHandler(editingModelConfig)"
                :loading="dialogTestLoading"
                :disabled="!editingModelConfig?.id"
              >
                测试连接
              </el-button>
            </template>
          </el-input>
          <div class="form-tip" v-if="!editingModelConfig?.id">
            <el-text type="warning" size="small">保存配置后可用此处测试；新建时也可在列表中启用后测试。</el-text>
          </div>
        </el-form-item>
        
        <el-form-item label="模型名称" prop="model_name">
          <el-input v-model="modelConfigForm.model_name" placeholder="请输入模型名称" />
        </el-form-item>

        <div v-if="modelConfigForm.model_type === 'vision'" class="form-tip vision-model-tip">
          <el-text type="info" size="small">
            视觉模型须支持识图（OpenAI 兼容 <code>chat/completions</code> + 图片输入）。
            推荐：<code>qwen-vl-max</code>、<code>gpt-4o</code>；API 地址填 Base URL（以 <code>/v1</code> 结尾，如
            <code>https://dashscope.aliyuncs.com/compatible-mode/v1</code>），保存后设为<strong>视觉默认</strong>并测试连接。
          </el-text>
        </div>
      </el-form>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="cancelModelEdit">取消</el-button>
          <el-button type="primary" @click="saveModelConfiguration" :loading="saving">
            保存
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, h, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { Connection, Search, Plus, ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import BackButton from '@/components/BackButton.vue'
import dayjs from 'dayjs'
import {
  getLLMConfigurations,
  createLLMConfiguration,
  updateLLMConfiguration,
  deleteLLMConfiguration,
  testLLMConnection,
  toggleLLMConfigurationActive,
  setLLMConfigurationDefault,
} from '@/api/aiConfig'

// 响应式数据
const loading = ref(false)
const saving = ref(false)
const testingConnection = ref(null)
/** 正在设为默认的配置 id（用于行内 Link loading） */
const settingDefaultId = ref(null)
const showCreateModelDialog = ref(false)
const editingModelConfig = ref(null)
const searchQuery = ref('')
const modelTypeFilter = ref('')
// 配置提示折叠面板：默认收起，由用户按需展开
const configTipsActiveNames = ref([])

// 数据
const configurations = ref([])

/** 本地私有化默认 OpenAI 兼容 Base URL（Ollama） */
const LOCAL_DEFAULT_BASE_URL = 'http://localhost:11434/v1'

// 模型表单数据（deploy_mode: 0=云端，1=本地；纯前端状态，后端无列时会忽略该字段）
const modelConfigForm = reactive({
  model_type: 'llm',
  provider: '',
  deploy_mode: 0,
  api_key: '',
  base_url: '',
  model_name: '',
  is_active: true
})

// 模型表单验证规则
const modelConfigRules = {
  model_type: [
    { required: true, message: '请选择模型类型', trigger: 'change' }
  ],
  provider: [
    { required: true, message: '请选择模型提供商', trigger: 'change' }
  ],
  api_key: [
    { 
      validator: (rule, value, callback) => {
        // 编辑模式下，如果API密钥为空，允许通过（不修改现有密钥）
        if (editingModelConfig.value && !value) {
          callback()
          return
        }

        // 本地私有化：不强制 API 密钥（不再依赖 provider === 'ollama'）
        if (modelConfigForm.deploy_mode === 1) {
          callback()
          return
        }
        
        // Ollama提供商不需要API密钥
        const provider = modelConfigForm.provider
        if (provider === 'ollama') {
          callback()
          return
        }
        
        // 其他提供商需要API密钥
        if (provider && ['openai', 'deepseek'].includes(provider)) {
          if (!value || value.trim() === '') {
            callback(new Error(`${provider === 'openai' ? 'OpenAI' : 'DeepSeek'}需要提供API密钥`))
            return
          }
        }
        
        callback()
      },
      trigger: 'blur'
    }
  ],
  base_url: [
    { required: true, message: '请输入API地址', trigger: 'blur' },
    { type: 'url', message: '请输入有效的URL地址', trigger: 'blur' }
  ],
  model_name: [
    { required: true, message: '请输入模型名称', trigger: 'blur' }
  ]
}

// 计算属性
const filteredConfigurations = computed(() => {
  let result = configurations.value

  if (searchQuery.value) {
    result = result.filter(config => 
      config.model_name.toLowerCase().includes(searchQuery.value.toLowerCase())
    )
  }

  if (modelTypeFilter.value) {
    result = result.filter(config => config.model_type === modelTypeFilter.value)
  }

  return result
})

/** 是否已有视觉模型配置（用于 Web 视觉断言引导） */
const hasVisionConfiguration = computed(() =>
  configurations.value.some((c) => c.model_type === 'vision')
)

/** 操作列：按 model_type 区分默认文案 */
const getDefaultActionText = (row) => {
  if (settingDefaultId.value === row.id) return '设置中…'
  const isVision = row.model_type === 'vision'
  if (row.is_default) return isVision ? '视觉默认' : 'LLM默认'
  return isVision ? '设为视觉默认' : '设为 LLM 默认'
}

// 表单引用
const modelConfigFormRef = ref()

/** 打开/重置表单时暂停 deploy_mode 副作用，避免回填编辑数据时被 watch 覆盖 base_url */
const pauseDeployModeWatch = ref(false)

/**
 * 根据已保存数据推断部署模式：1=本地私有化，0=云端（与表单逻辑对齐，便于列表展示）
 */
const inferDeployModeFromConfig = (config) => {
  const ex = config.extra_config
  if (ex && (ex.deploy_mode === 1 || ex.deploy_mode === '1')) return 1
  const url = (config.base_url || '').toLowerCase()
  if (url.includes('localhost:11434') || url.includes('127.0.0.1:11434')) return 1
  if (url.includes(':11434')) return 1
  if (config.provider === 'ollama') return 1
  return 0
}

/** 表格列：部署模式文案 */
const getDeployModeLabel = (row) => (inferDeployModeFromConfig(row) === 1 ? '本地' : '云端')

/** 表格列：el-tag 类型（本地绿色 success、云端蓝色 primary） */
const getDeployModeTagType = (row) => (inferDeployModeFromConfig(row) === 1 ? 'success' : 'primary')

// deploy_mode 与用户操作联动：本地默认填 Ollama 地址并清空密钥；云端清空 base_url 由用户填写
watch(
  () => modelConfigForm.deploy_mode,
  async (mode) => {
    if (pauseDeployModeWatch.value) return
    if (mode === 1) {
      modelConfigForm.base_url = LOCAL_DEFAULT_BASE_URL
      modelConfigForm.api_key = ''
    } else {
      modelConfigForm.base_url = ''
    }
    await nextTick()
    modelConfigFormRef.value?.clearValidate(['api_key', 'base_url'])
  }
)

/** 弹窗内「测试连接」按钮 loading（后端仅支持按 config_id 测试，故仅编辑已存在记录时可用） */
const dialogTestLoading = computed(() => {
  const id = editingModelConfig.value?.id
  return id != null && testingConnection.value === id
})

// 方法
const loadConfigurations = async () => {
  try {
    loading.value = true
    const response = await getLLMConfigurations()
    
    if (response?.data) {
      if (Array.isArray(response.data)) {
        configurations.value = response.data
      } else if (response.data.items && Array.isArray(response.data.items)) {
        configurations.value = response.data.items
      } else if (response.data.success && response.data.data) {
        configurations.value = Array.isArray(response.data.data) ? response.data.data : []
      } else {
        configurations.value = []
      }
    } else {
      configurations.value = []
    }
  } catch (error) {
    console.error('加载模型配置失败:', error)
    ElMessage.error('加载模型配置失败')
  } finally {
    loading.value = false
  }
}


const onModelTypeChange = () => {
  modelConfigForm.provider = ''
  modelConfigForm.deploy_mode = 0
  modelConfigForm.api_key = ''
  modelConfigForm.model_name = ''
  modelConfigForm.base_url = ''
}

// 通用表单重置函数
const resetForm = (formRef, defaultValues) => {
  Object.assign(formRef, defaultValues)
}

/** 在 nextTick 后恢复 deploy_mode 的 watch，避免回填时误触本地/云端副作用 */
const resetFormWithDeployGuard = async (defaults) => {
  pauseDeployModeWatch.value = true
  resetForm(modelConfigForm, defaults)
  await nextTick()
  pauseDeployModeWatch.value = false
}

// 模型配置相关
const addModelConfiguration = async () => {
  editingModelConfig.value = null
  await resetFormWithDeployGuard({
    model_type: 'llm',
    provider: '',
    deploy_mode: 0,
    api_key: '',
    base_url: '',
    model_name: '',
    is_active: true
  })
  showCreateModelDialog.value = true
}

/** 从「未配置视觉模型」引导直接打开创建表单并预选视觉类型 */
const addVisionModelConfiguration = async () => {
  editingModelConfig.value = null
  await resetFormWithDeployGuard({
    model_type: 'vision',
    provider: '',
    deploy_mode: 0,
    api_key: '',
    base_url: '',
    model_name: '',
    is_active: true
  })
  showCreateModelDialog.value = true
}

const editConfiguration = async (config) => {
  editingModelConfig.value = config
  await resetFormWithDeployGuard({
    model_type: config.model_type,
    provider: config.provider || '',
    deploy_mode: inferDeployModeFromConfig(config),
    api_key: config.api_key || '',
    base_url: config.base_url,
    model_name: config.model_name,
    is_active: config.is_active
  })
  showCreateModelDialog.value = true
}

const saveModelConfiguration = async () => {
  try {
    await modelConfigFormRef.value.validate()
    saving.value = true

    const data = { ...modelConfigForm }
    
    if (editingModelConfig.value && !data.api_key) {
      delete data.api_key
    }

    if (editingModelConfig.value) {
      await updateLLMConfiguration(editingModelConfig.value.id, data)
      ElMessage.success('模型配置更新成功')
    } else {
      await createLLMConfiguration(data)
      ElMessage.success('模型配置创建成功')
    }

    showCreateModelDialog.value = false
    await loadConfigurations()
  } catch (error) {
    console.error('保存模型配置失败:', error)
    ElMessage.error('保存模型配置失败')
  } finally {
    saving.value = false
  }
}

const cancelModelEdit = async () => {
  showCreateModelDialog.value = false
  editingModelConfig.value = null
  await resetFormWithDeployGuard({
    model_type: 'llm',
    provider: '',
    deploy_mode: 0,
    api_key: '',
    base_url: '',
    model_name: '',
    is_active: true
  })
  modelConfigFormRef?.value?.resetFields()
}

/** 本地/私有化模型连接失败时展示的固定引导文案（列表与弹窗测试共用逻辑依据 inferDeployModeFromConfig） */
const LOCAL_MODEL_TEST_FAIL_HINT =
  '连接失败，请检查本地是否已安装本模型、推理服务是否已启动（例如 Ollama 是否运行、是否已执行 ollama pull 拉取模型），并确认 API 地址与模型名称填写正确。'

/**
 * 连接测试失败时的提示：本地模型用更友好的说明 + 可选服务端原文；云端保持简短错误信息。
 */
const showTestConnectionFailure = (config, serverMessage) => {
  const isLocal = inferDeployModeFromConfig(config) === 1
  const detail = (serverMessage || '').trim()
  const detailWorthShowing = detail && detail !== '连接测试失败'

  if (isLocal) {
    const children = [
      h('div', { style: 'margin-bottom: 10px; line-height: 1.5; color: #606266;' }, LOCAL_MODEL_TEST_FAIL_HINT),
    ]
    if (detailWorthShowing) {
      children.push(
        h(
          'div',
          {
            style:
              'font-size: 12px; color: #909399; border-top: 1px solid #ebeef5; padding-top: 8px; line-height: 1.5;',
          },
          `详情：${detail}`
        )
      )
    }
    ElNotification({
      title: '本地模型连接失败',
      message: h('div', children),
      type: 'error',
      duration: 12000,
      showClose: true,
    })
    return
  }

  ElMessage.error(detail ? `连接测试失败: ${detail}` : '连接测试失败')
}

const testConnectionHandler = async (config) => {
  if (!config?.id) {
    ElMessage.warning('请先保存配置后再测试连接。新建记录保存后可在列表或此处再次测试。')
    return
  }
  try {
    testingConnection.value = config.id
    
    const response = await testLLMConnection({ config_id: config.id })
    
    console.log('模型连接测试API响应:', response)

    let data = null
    if (response && response.data) {
      if (response.data.success && response.data.data) {
        data = response.data.data
      } else {
        data = response.data
      }
    }

    if (data && data.success) {
      ElNotification({
        title: '连接测试成功',
        message: h('div', [
          h('div', { style: 'margin-bottom: 8px;' }, `${config.model_name} 连接测试成功！`),
          h('div', { style: 'font-size: 12px; color: #67c23a;' }, `⏱️ 响应时间: ${data.response_time}s`),
          data.response_content && h('div', { 
            style: 'font-size: 12px; color: #909399; border-top: 1px solid #ebeef5; padding-top: 8px;' 
          }, `📝 响应内容: ${data.response_content}`)
        ]),
        type: 'success',
        duration: 5000,
        showClose: true
      })
    } else {
      const errorMsg = (data && data.message) || response?.error || '连接测试失败'
      showTestConnectionFailure(config, errorMsg)
    }
  } catch (error) {
    console.error('连接测试失败:', error)
    const isLocal = inferDeployModeFromConfig(config) === 1

    if (error.response?.data) {
      const errorData = error.response.data
      const serverDetail = [
        errorData.error_detail,
        typeof errorData.message === 'string' ? errorData.message : '',
        typeof errorData.detail === 'string' ? errorData.detail : '',
      ]
        .map((s) => (s || '').trim())
        .find(Boolean) || ''
      const errorTitle = isLocal ? '本地模型连接失败' : getErrorTitle(errorData.error_type)

      if (isLocal) {
        ElNotification({
          title: errorTitle,
          message: h('div', [
            h('div', { style: 'margin-bottom: 10px; line-height: 1.5; color: #606266;' }, LOCAL_MODEL_TEST_FAIL_HINT),
            serverDetail &&
              serverDetail !== '连接测试失败' &&
              h(
                'div',
                {
                  style:
                    'font-size: 12px; color: #909399; border-top: 1px solid #ebeef5; padding-top: 8px; line-height: 1.5;',
                },
                `服务端返回：${serverDetail}`
              ),
            errorData.suggestion &&
              h(
                'div',
                {
                  style:
                    'font-size: 12px; color: #67c23a; border-top: 1px solid #ebeef5; padding-top: 8px; line-height: 1.5;',
                },
                `建议：${errorData.suggestion}`
              ),
          ]),
          type: 'error',
          duration: 12000,
          showClose: true,
        })
      } else {
        ElNotification({
          title: errorTitle,
          message: h('div', [
            h('div', { style: 'margin-bottom: 8px;' }, errorData.error_detail || serverDetail),
            errorData.suggestion &&
              h('div', {
                style: 'font-size: 12px; color: #909399; border-top: 1px solid #ebeef5; padding-top: 8px;',
              }, `💡 建议: ${errorData.suggestion}`),
          ]),
          type: 'error',
          duration: 8000,
          showClose: true,
        })
      }
    } else {
      if (isLocal) {
        ElNotification({
          title: '本地模型连接失败',
          message: h('div', [
            h('div', { style: 'margin-bottom: 8px; line-height: 1.5; color: #606266;' }, LOCAL_MODEL_TEST_FAIL_HINT),
            h('div', { style: 'font-size: 12px; color: #909399;' }, '未收到服务器响应，请检查本机网络、代理或后端服务是否正常。'),
          ]),
          type: 'error',
          duration: 12000,
          showClose: true,
        })
      } else {
        ElMessage.error('网络错误，请检查网络连接')
      }
    }
  } finally {
    testingConnection.value = null
  }
}

/** 将当前行设为该模型类型下的默认 LLM（后端会清除同类型其他默认并启用本条） */
const setAsDefaultHandler = async (row) => {
  if (row.is_default) return
  try {
    settingDefaultId.value = row.id
    await setLLMConfigurationDefault(row.id)
    const typeLabel = row.model_type === 'vision' ? '视觉' : 'LLM'
    ElMessage.success(`已设为${typeLabel}默认模型配置`)
    await loadConfigurations()
  } catch (error) {
    console.error('设为默认失败:', error)
    ElMessage.error(error.response?.data?.message || error.message || '设为默认失败')
  } finally {
    settingDefaultId.value = null
  }
}

// 切换模型状态
const toggleModelStatus = async (config) => {
  try {
    config.statusLoading = true
    const originalStatus = config.is_active
    const newStatus = !originalStatus
    
    await toggleLLMConfigurationActive(config.id)
    config.is_active = newStatus
    
    ElMessage.success(newStatus ? '模型配置已启用' : '模型配置已禁用')
  } catch (error) {
    console.error('切换模型状态失败:', error)
    ElMessage.error(`切换模型状态失败: ${error.response?.data?.message || error.message}`)
    config.is_active = !config.is_active
  } finally {
    config.statusLoading = false
  }
}

// 删除模型配置
const handleDeleteModelConfiguration = async (config) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除配置 "${config.model_name}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await deleteLLMConfiguration(config.id)
    ElMessage.success('配置删除成功')
    await loadConfigurations()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除配置失败:', error)
      ElMessage.error('删除配置失败')
    }
  }
}

// 工具方法
const getErrorTitle = (errorType) => {
  const titles = {
    'VALIDATION_ERROR': '参数验证错误',
    'NOT_FOUND_ERROR': '配置不存在',
    'CONFIG_ERROR': '配置状态错误',
    'AUTH_ERROR': '认证失败',
    'CONNECTION_ERROR': '连接失败',
    'TIMEOUT_ERROR': '请求超时',
    'GENERAL_ERROR': '连接测试失败'
  }
  return titles[errorType] || '连接测试失败'
}

const formatDate = (dateString) => {
  return dayjs(dateString).format('YYYY-MM-DD HH:mm:ss')
}

// 通用图标工具函数
const getIconText = (name, defaultChar = 'A') => {
  if (!name) return defaultChar
  return name.charAt(0).toUpperCase()
}

const getIconColor = (name, defaultColor = '#409EFF') => {
  if (!name) return defaultColor
  
  const firstChar = name.charAt(0).toLowerCase()
  const colors = {
    'a': '#FF6B6B', 'b': '#4ECDC4', 'c': '#45B7D1', 'd': '#96CEB4', 'e': '#FFEAA7',
    'f': '#DDA0DD', 'g': '#98D8C8', 'h': '#F7DC6F', 'i': '#BB8FCE', 'j': '#85C1E9',
    'k': '#F8C471', 'l': '#82E0AA', 'm': '#F1948A', 'n': '#85C1E9', 'o': '#F7DC6F',
    'p': '#D7BDE2', 'q': '#A9DFBF', 'r': '#F9E79F', 's': '#AED6F1', 't': '#A3E4D7',
    'u': '#D5DBDB', 'v': '#FADBD8', 'w': '#D1F2EB', 'x': '#E8DAEF', 'y': '#FCF3CF',
    'z': '#D6EAF8'
  }
  
  return colors[firstChar] || defaultColor
}

const getModelIconText = (name) => getIconText(name, 'A')
const getModelIconColor = (name) => getIconColor(name, '#409EFF')

// 初始化
onMounted(() => {
  loadConfigurations()
})
</script>

<style scoped>
.llm-config-page {
  margin: 0 auto;
}

.dual-default-alert {
  margin: 0 16px 12px;
}

.vision-empty-hint {
  margin: 0 0 16px;
}

.vision-empty-hint .vision-add-link {
  margin-left: 8px;
  vertical-align: baseline;
}

.vision-model-tip {
  margin: -8px 0 0 120px;
  line-height: 1.6;
}

.vision-model-tip code {
  font-size: 12px;
}

/* 配置注意事项折叠区块 */
.config-tips-wrapper {
  margin: 12px 0 16px;
  padding: 0 16px;
}

.config-tips-header {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.config-tips-header .tips-icon {
  font-size: 16px;
  margin-right: 4px;
}

.config-tips-header .tips-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.config-tips-header .tips-arrow {
  margin-left: 8px;
  color: #909399;
  display: inline-flex;
  align-items: center;
}

.config-tips-header .tips-title {
  font-weight: 600;
  font-size: 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.config-tips-header .tips-subtitle {
  font-size: 12px;
  color: #909399;
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.config-tips-body {
  padding: 8px 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 24px;
}

.tips-section-title {
  font-weight: 600;
  margin-bottom: 6px;
  font-size: 13px;
}

.tips-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}

.tips-list li + li {
  margin-top: 2px;
}

.tips-label {
  font-weight: 600;
  color: #303133;
}

.tips-list code {
  font-family: Menlo, Monaco, Consolas, 'Courier New', monospace;
  font-size: 12px;
  padding: 1px 4px;
  border-radius: 3px;
  background-color: #f4f4f5;
  border: 1px solid #e4e7ed;
}

.tips-list strong {
  font-weight: 600;
}

/* 页面头部样式 */
.page-header {
  margin-bottom: 20px;
}

.page-header :deep(.back-btn) {
  margin-bottom: 12px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16px 16px 0 0;
  padding: 20px 32px;
  color: white;
  box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
  position: relative;
  z-index: 1;
  overflow: hidden;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: auto;
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

.config-list-card {
  margin-bottom: 20px;
  border-radius: 0 0 16px 16px;
  border-top: none;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  gap: 20px;
}

.card-header-left {
  display: flex;
  align-items: center;
  flex-grow: 1;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.card-icon {
  font-size: 18px;
  color: #409eff;
}

.card-header-right {
  display: flex;
  gap: 10px;
  align-items: center;
}

/* 配置名称列样式 */
.config-name {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.config-icon-wrapper {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.config-icon-wrapper:hover {
  transform: scale(1.05);
}

/* AI模型图标样式 */
.model-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  min-width: 40px;
  height: 40px;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.model-icon-wrapper:hover {
  transform: scale(1.1);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.model-icon-text {
  color: white;
  font-weight: bold;
  font-size: 16px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
  user-select: none;
}

.config-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-title {
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.2;
  display: flex;
  align-items: center;
}

.config-model {
  font-size: 12px;
  color: #909399;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 添加配置按钮样式 */
.add-config-btn {
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: white;
  backdrop-filter: blur(10px);
  font-weight: 500;
  padding: 12px 24px;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.add-config-btn:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}


.dialog-footer {
  text-align: right;
}

/* 表格样式优化 */
.el-table {
  border-radius: 8px;
  overflow: hidden;
}

.el-table .el-table__row {
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.el-table .el-table__row:hover {
  background-color: #f5f7fa !important;
}

/* 部署模式 radio：与表单对齐 */
.deploy-mode-radio {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
}

.deploy-mode-tip {
  margin-top: 8px;
}

/* API 地址 + 测试连接一体化输入 */
.base-url-input :deep(.el-input-group__append) {
  padding: 0;
  background: var(--el-fill-color-blank);
}

.base-url-input :deep(.el-input-group__append .el-button) {
  margin: 0;
  border: none;
  border-radius: 0;
  padding: 0 16px;
  font-weight: 500;
}

.base-url-input :deep(.el-input-group__append .el-button:hover) {
  color: var(--el-color-primary);
}

/* 表单提示样式 */
.form-tip {
  margin-top: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.form-tip .el-text {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 信息类型提示样式 */
.form-tip .el-text[type="info"] {
  background-color: #f0f9ff;
  border: 1px solid #b3d8ff;
  color: #409eff;
}

/* 表格：部署模式标签略扁、易读 */
.deploy-mode-table-tag {
  font-weight: 500;
  min-width: 52px;
  justify-content: center;
}

/* 操作列：Link + 按钮换行与间距 */
.table-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.table-actions .set-default-link {
  font-size: 13px;
  margin-right: 4px;
}

.table-actions .set-default-link.is-disabled {
  color: var(--el-text-color-secondary);
  cursor: not-allowed;
}


/* 响应式设计 */
@media (max-width: 768px) {
  .llm-config-page {
    padding: 10px;
  }

  .config-tips-wrapper {
    padding: 0;
  }

  .config-tips-body {
    grid-template-columns: minmax(0, 1fr);
    gap: 8px 0;
  }

  .page-header {
    padding: 20px;
    margin-bottom: 16px;
  }

  .header-content {
    flex-direction: column;
    gap: 20px;
    text-align: center;
  }

  .header-left h2 {
    font-size: 20px;
  }

  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 15px;
  }

  .card-header-right {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .config-name {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .config-icon-wrapper {
    width: 32px;
    height: 32px;
  }
}
</style>
