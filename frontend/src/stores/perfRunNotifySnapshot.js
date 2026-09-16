import { defineStore } from 'pinia'
import { shallowRef } from 'vue'

/**
 * 与 MainLayout 全局压测监听共用：记录各场景上次 last_execution_status，用于 running -> 终态 差分。
 */
export const usePerfRunNotifySnapshotStore = defineStore('perfRunNotifySnapshot', () => {
  const lastStatusByScenarioId = shallowRef({})

  function peekSnapshot() {
    return { ...lastStatusByScenarioId.value }
  }

  /** @param {Array<{ id: number, last_execution_status?: string | null }>} rows */
  function applyScenarioRows(rows) {
    const next = { ...lastStatusByScenarioId.value }
    for (const r of rows || []) {
      if (r?.id != null) next[r.id] = r.last_execution_status ?? null
    }
    lastStatusByScenarioId.value = next
  }

  /** 启动成功后乐观标记为 running，避免极短任务在两次轮询间结束时漏掉「完成」通知 */
  function markScenarioStatus(scenarioId, status) {
    if (scenarioId == null) return
    lastStatusByScenarioId.value = {
      ...lastStatusByScenarioId.value,
      [scenarioId]: status
    }
  }

  return { lastStatusByScenarioId, peekSnapshot, applyScenarioRows, markScenarioStatus }
})
