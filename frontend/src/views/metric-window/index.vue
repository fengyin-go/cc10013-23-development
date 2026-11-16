<template>
  <section class="page" data-module="metric-window">
    <header class="page-head">
      <div>
        <h2>指标联合窗口</h2>
        <p class="page-desc">
          按指标编号与时间窗把成功率、延迟、错误率组成联合窗口，三项样本联合计算；
          每个窗口只保留一个可解释结论，并随判定版本保存发布依据。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="switchTab('ingest')">录入指标样本</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statsCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <nav class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-item"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- 联合窗口列表 -->
    <div v-if="activeTab === 'windows'">
      <form class="filter-bar" @submit.prevent="reloadWindows(1)">
        <label class="filter-item">
          <span>指标编号</span>
          <input v-model="windowFilters.keyword" placeholder="按指标编号搜索" />
        </label>
        <label class="filter-item">
          <span>窗口状态</span>
          <select v-model="windowFilters.status">
            <option value="">全部状态</option>
            <option v-for="s in windowStatuses" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>关联端点</span>
          <input v-model="windowFilters.endpoint" placeholder="按端点编号筛选" />
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetWindowFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>窗口编号</th>
            <th>指标编号</th>
            <th>关联端点</th>
            <th>时间窗</th>
            <th>判定版本</th>
            <th>联合结论</th>
            <th>异常项</th>
            <th>窗口状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in windows" :key="row.id" :class="{ 'row-abnormal': row.abnormal }">
            <td>{{ row['窗口编号'] }}</td>
            <td>{{ row['指标编号'] }}</td>
            <td>
              <span :class="{ 'endpoint-flag': row.abnormal }">{{ row['关联端点'] }}</span>
            </td>
            <td>{{ row['时间窗'] }}</td>
            <td>{{ row['判定版本'] }}</td>
            <td>
              <span class="conclusion-tag" :class="row['联合结论'] === '异常' ? 'tag-bad' : 'tag-ok'">
                {{ row['联合结论'] }}
              </span>
            </td>
            <td>{{ row['异常项']?.length ? row['异常项'].join('、') : '—' }}</td>
            <td>{{ row['状态'] }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="openDetail(row.id)">结果详情</button>
            </td>
          </tr>
          <tr v-if="!windows.length">
            <td colspan="9" class="empty-state">暂无联合窗口，可先录入三项指标样本</td>
          </tr>
        </tbody>
      </table>
      <Pagination :page="windowPage.page" :size="windowPage.size" :total="windowPage.total" @change="reloadWindows" />
    </div>

    <!-- 监控待处理队列 -->
    <div v-if="activeTab === 'todos'">
      <form class="filter-bar" @submit.prevent="reloadTodos(1)">
        <label class="filter-item">
          <span>指标编号 / 端点</span>
          <input v-model="todoFilters.keyword" placeholder="按指标编号或端点搜索" />
        </label>
        <label class="filter-item">
          <span>优先级</span>
          <select v-model="todoFilters.priority">
            <option value="">全部优先级</option>
            <option value="高">高</option>
            <option value="中">中</option>
            <option value="低">低</option>
          </select>
        </label>
        <label class="filter-item">
          <span>处理状态</span>
          <select v-model="todoFilters.status">
            <option value="">全部</option>
            <option value="待处理">待处理</option>
            <option value="已处理">已处理</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetTodoFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>待办编号</th>
            <th>待办类型</th>
            <th>优先级</th>
            <th>指标编号</th>
            <th>关联端点</th>
            <th>时间窗</th>
            <th>判定版本</th>
            <th>指标结果摘要</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in todos" :key="row.id" :class="{ 'row-abnormal': row['待办类型'] === '迟到裁决' }">
            <td>{{ row['待办编号'] }}</td>
            <td>{{ row['待办类型'] }}</td>
            <td>
              <span class="priority-tag" :class="row['优先级'] === '高' ? 'tag-bad' : 'tag-mid'">{{ row['优先级'] }}</span>
            </td>
            <td>{{ row['指标编号'] }}</td>
            <td><span class="endpoint-flag">{{ row['关联端点'] }}</span></td>
            <td>{{ row['时间窗'] }}</td>
            <td>{{ row['判定版本'] }}</td>
            <td class="summary-cell">{{ row['指标结果摘要'] }}</td>
            <td>{{ row['状态'] }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="openDetail(row['窗口ID'])">回到同一窗口</button>
            </td>
          </tr>
          <tr v-if="!todos.length">
            <td colspan="10" class="empty-state">暂无待办记录</td>
          </tr>
        </tbody>
      </table>
      <Pagination :page="todoPage.page" :size="todoPage.size" :total="todoPage.total" @change="reloadTodos" />
    </div>

    <!-- 采集指标样本 -->
    <div v-if="activeTab === 'samples'">
      <form class="filter-bar" @submit.prevent="reloadSamples(1)">
        <label class="filter-item">
          <span>指标编号 / 样本编号</span>
          <input v-model="sampleFilters.keyword" placeholder="按指标编号或样本编号搜索" />
        </label>
        <label class="filter-item">
          <span>关联端点</span>
          <input v-model="sampleFilters.endpoint" placeholder="按端点筛选" />
        </label>
        <label class="filter-item check-item">
          <input v-model="sampleFilters.abnormalOnly" type="checkbox" />
          <span>只看异常样本</span>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetSampleFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>样本编号</th>
            <th>指标编号</th>
            <th>关联端点</th>
            <th>时间窗</th>
            <th>指标类型</th>
            <th>样本值</th>
            <th>阈值</th>
            <th>单指标判定</th>
            <th>到达批次</th>
            <th>是否迟到</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in samples" :key="row.id" :class="{ 'row-abnormal': row['异常标记'] }">
            <td>{{ row['样本编号'] }}</td>
            <td>{{ row['指标编号'] }}</td>
            <td><span :class="{ 'endpoint-flag': row['异常标记'] }">{{ row['关联端点'] }}</span></td>
            <td>{{ row['时间窗'] }}</td>
            <td>{{ row['指标类型'] }}</td>
            <td>{{ row['样本值'] }}</td>
            <td>{{ row['阈值'] }}</td>
            <td>
              <span class="conclusion-tag" :class="row['判定'] === '超限' ? 'tag-bad' : 'tag-ok'">{{ row['判定'] }}</span>
            </td>
            <td>{{ row['到达批次'] }}</td>
            <td>{{ row['是否迟到'] ? '迟到' : '准时' }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="backToWindow(row)">回到同一窗口</button>
            </td>
          </tr>
          <tr v-if="!samples.length">
            <td colspan="11" class="empty-state">暂无指标样本</td>
          </tr>
        </tbody>
      </table>
      <Pagination :page="samplePage.page" :size="samplePage.size" :total="samplePage.total" @change="reloadSamples" />
    </div>

    <!-- 样本录入 -->
    <form v-if="activeTab === 'ingest'" class="ingest-form" @submit.prevent="submitSample">
      <p class="page-desc">三项指标、窗口身份（指标编号 + 时间窗）与判定版本随样本一起写入；样本在结论发布后到达将自动标记迟到并进入裁决队列。</p>
      <div class="form-grid">
        <label v-for="field in sampleFormFields" :key="field.name" class="filter-item">
          <span>{{ field.label }}</span>
          <select v-if="field.type === 'select'" v-model="sampleForm[field.name]">
            <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
          </select>
          <input
            v-else
            v-model="sampleForm[field.name]"
            :type="field.type === 'number' ? 'number' : 'text'"
            :placeholder="field.placeholder"
          />
        </label>
      </div>
      <div class="form-actions">
        <button class="btn primary" type="submit">提交样本</button>
        <button class="btn ghost" type="button" @click="resetSampleForm">清空</button>
      </div>
    </form>

    <footer class="page-foot">
      <span v-if="actionMessage" :class="actionOk ? 'ok-text' : 'error-text'">{{ actionMessage }}</span>
    </footer>

    <!-- 窗口结果详情抽屉 -->
    <div v-if="detail" class="drawer-mask" @click.self="closeDetail">
      <div class="drawer">
        <header class="drawer-head">
          <h3>联合窗口结果详情 · {{ detail.window['窗口编号'] }}</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>

        <section class="detail-block">
          <h4>窗口身份与判定版本</h4>
          <table class="data-table">
            <tbody>
              <tr><th>指标编号</th><td>{{ detail.window['指标编号'] }}</td><th>关联端点</th><td>{{ detail.window['关联端点'] }}</td></tr>
              <tr><th>时间窗</th><td>{{ detail.window['时间窗'] }}</td><th>判定版本</th><td>{{ detail.window['判定版本'] }}</td></tr>
              <tr>
                <th>联合结论</th>
                <td>
                  <span class="conclusion-tag" :class="detail.window['联合结论'] === '异常' ? 'tag-bad' : 'tag-ok'">
                    {{ detail.window['联合结论'] }}
                  </span>
                </td>
                <th>窗口状态</th><td>{{ detail.window['状态'] }}</td>
              </tr>
              <tr v-if="detail.window['冲突说明']">
                <th>迟到冲突</th>
                <td colspan="3" class="conflict-cell">{{ detail.window['冲突说明'] }}</td>
              </tr>
              <tr>
                <th>结论说明</th>
                <td colspan="3" class="summary-cell">{{ detail.window['结论说明'] }}</td>
              </tr>
            </tbody>
          </table>
          <div class="detail-actions">
            <button
              v-if="detail.window['状态'] === '采集中'"
              class="btn primary"
              type="button"
              @click="publish(detail.window.id)"
            >
              发布联合结论
            </button>
            <button
              v-if="detail.window['状态'] !== '采集中'"
              class="btn"
              type="button"
              @click="retest(detail.window.id)"
            >
              复测生成新版本
            </button>
            <template v-if="openLateTodo">
              <button class="btn primary" type="button" @click="arbitrate(detail.window.id, '维持原结论')">
                裁决：维持原结论
              </button>
              <button class="btn primary" type="button" @click="arbitrate(detail.window.id, '采纳更正')">
                裁决：采纳更正
              </button>
            </template>
          </div>
        </section>

        <section class="detail-block">
          <h4>原始样本（指标编号 + 时间窗可回溯，迟到样本单独标出，异常端点联动标红）</h4>
          <table class="data-table">
            <thead>
              <tr>
                <th>样本编号</th><th>指标类型</th><th>样本值</th><th>阈值</th>
                <th>单指标判定</th><th>到达批次</th><th>迟到/生效</th><th>采集时间</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="s in detail.samples"
                :key="s.id"
                :class="{ 'row-abnormal': s['异常标记'], 'row-inactive': !s['生效中'] }"
              >
                <td>{{ s['样本编号'] }}</td>
                <td>{{ s['指标类型'] }}</td>
                <td>{{ s['样本值'] }}</td>
                <td>{{ s['阈值'] }}</td>
                <td>
                  <span class="conclusion-tag" :class="s['判定'] === '超限' ? 'tag-bad' : 'tag-ok'">{{ s['判定'] }}</span>
                </td>
                <td>{{ s['到达批次'] }}</td>
                <td>
                  <span v-if="s['是否迟到']" class="late-tag">迟到{{ s['生效中'] ? '·已采纳' : '·待裁决' }}</span>
                  <span v-else class="page-desc">准时{{ s['生效中'] ? '·生效中' : '' }}</span>
                </td>
                <td>{{ s['采集时间'] }}</td>
              </tr>
              <tr v-if="!detail.samples.length">
                <td colspan="8" class="empty-state">样本尚未到齐</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="detail-block">
          <h4>版本记录与发布依据（已发布窗口保存当时依据）</h4>
          <div v-for="record in detail['版本记录']" :key="record['判定版本'] + record['来源']" class="version-card">
            <div class="version-head">
              <strong>{{ record['判定版本'] }} · {{ record['来源'] }}</strong>
              <span>结论：{{ record['联合结论'] }}</span>
              <span class="page-desc">{{ record['依据时间'] }}</span>
            </div>
            <p class="summary-cell">{{ record['结论说明'] }}</p>
            <p class="page-desc">
              样本引用：成功率 {{ record['样本引用']['成功率'] ?? '—' }} ／
              延迟 {{ record['样本引用']['延迟'] ?? '—' }} ／
              错误率 {{ record['样本引用']['错误率'] ?? '—' }}
            </p>
          </div>
        </section>

        <section v-if="detail.todos.length" class="detail-block">
          <h4>关联待办</h4>
          <table class="data-table">
            <thead>
              <tr><th>待办编号</th><th>类型</th><th>优先级</th><th>状态</th><th>处理方式</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in detail.todos" :key="t.id">
                <td>{{ t['待办编号'] }}</td>
                <td>{{ t['待办类型'] }}</td>
                <td>{{ t['优先级'] }}</td>
                <td>{{ t['状态'] }}</td>
                <td>{{ t['处理方式'] ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/metric-window'

type WindowRow = Record<string, any>
type SampleRow = Record<string, any>
type TodoRow = Record<string, any>
interface PageState {
  page: number
  size: number
  total: number
}
interface WindowDetail {
  window: WindowRow
  samples: SampleRow[]
  todos: TodoRow[]
  版本记录: Record<string, any>[]
}
interface Stats {
  联合窗口总数: number
  异常窗口数: number
  待处理待办数: number
  高优先级待办: number
  迟到冲突数: number
  指标样本总数: number
}

const tabs = [
  { key: 'windows', label: '联合窗口' },
  { key: 'todos', label: '待处理队列' },
  { key: 'samples', label: '指标样本' },
  { key: 'ingest', label: '样本录入' },
] as const
type TabKey = (typeof tabs)[number]['key']
const activeTab = ref<TabKey>('windows')
const windowStatuses = ['采集中', '已发布', '终态裁决']

const stats = ref<Stats>({
  联合窗口总数: 0, 异常窗口数: 0, 待处理待办数: 0, 高优先级待办: 0, 迟到冲突数: 0, 指标样本总数: 0,
})
const statsCards = computed(() => [
  { label: '联合窗口总数', value: stats.value.联合窗口总数 },
  { label: '异常窗口', value: stats.value.异常窗口数 },
  { label: '待处理待办', value: stats.value.待处理待办数 },
  { label: '高优先级待办', value: stats.value.高优先级待办 },
  { label: '迟到冲突', value: stats.value.迟到冲突数 },
  { label: '指标样本', value: stats.value.指标样本总数 },
])

const windows = ref<WindowRow[]>([])
const todos = ref<TodoRow[]>([])
const samples = ref<SampleRow[]>([])
const windowPage = reactive<PageState>({ page: 1, size: 10, total: 0 })
const todoPage = reactive<PageState>({ page: 1, size: 10, total: 0 })
const samplePage = reactive<PageState>({ page: 1, size: 10, total: 0 })

const windowFilters = reactive({ keyword: '', status: '', endpoint: '' })
const todoFilters = reactive({ keyword: '', priority: '', status: '' })
const sampleFilters = reactive({ keyword: '', endpoint: '', abnormalOnly: false })

const detail = ref<WindowDetail | null>(null)
const actionMessage = ref('')
const actionOk = ref(true)

const sampleFormFields = [
  { name: '指标编号', label: '指标编号', type: 'text', placeholder: '如 MONI-0005' },
  { name: '关联端点', label: '关联端点', type: 'text', placeholder: '如 ENDP-0005' },
  { name: '时间窗', label: '时间窗', type: 'text', placeholder: '如 2026-11-16 10:00' },
  { name: '指标类型', label: '指标类型', type: 'select', options: ['成功率', '延迟', '错误率'] },
  { name: '样本值', label: '样本值', type: 'number', placeholder: '实测数值' },
  { name: '阈值', label: '阈值', type: 'number', placeholder: '判定阈值' },
  { name: '到达批次', label: '到达批次', type: 'text', placeholder: '如 B-1000' },
  { name: '采集时间', label: '采集时间（可选）', type: 'text', placeholder: '默认取当前时间' },
] as const
const sampleForm = reactive<Record<string, string | number>>({
  指标编号: '', 关联端点: '', 时间窗: '', 指标类型: '成功率', 样本值: '', 阈值: '', 到达批次: '', 采集时间: '',
})

function buildQuery(filters: Record<string, string | boolean>, pageState: PageState): string {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value !== false) params.set(key, String(value))
  })
  params.set('page', String(pageState.page))
  params.set('size', String(pageState.size))
  return params.toString()
}

async function getJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) throw new Error(`接口返回 ${response.status}`)
  return (await response.json()) as T
}

async function reloadStats() {
  stats.value = await getJson<Stats>(`${ENDPOINT}/stats`)
}

async function reloadWindows(page?: number) {
  if (page) windowPage.page = page
  const payload = await getJson<{ items: WindowRow[]; total: number }>(
    `${ENDPOINT}/windows?${buildQuery(windowFilters, windowPage)}`,
  )
  windows.value = payload.items
  windowPage.total = payload.total
}

async function reloadTodos(page?: number) {
  if (page) todoPage.page = page
  const payload = await getJson<{ items: TodoRow[]; total: number }>(
    `${ENDPOINT}/todos?${buildQuery(todoFilters, todoPage)}`,
  )
  todos.value = payload.items
  todoPage.total = payload.total
}

async function reloadSamples(page?: number) {
  if (page) samplePage.page = page
  const payload = await getJson<{ items: SampleRow[]; total: number }>(
    `${ENDPOINT}/samples?${buildQuery(sampleFilters, samplePage)}`,
  )
  samples.value = payload.items
  samplePage.total = payload.total
}

function resetWindowFilters() {
  windowFilters.keyword = ''
  windowFilters.status = ''
  windowFilters.endpoint = ''
  void reloadWindows(1)
}

function resetTodoFilters() {
  todoFilters.keyword = ''
  todoFilters.priority = ''
  todoFilters.status = ''
  void reloadTodos(1)
}

function resetSampleFilters() {
  sampleFilters.keyword = ''
  sampleFilters.endpoint = ''
  sampleFilters.abnormalOnly = false
  void reloadSamples(1)
}

async function openDetail(windowId: number) {
  detail.value = await getJson<WindowDetail>(`${ENDPOINT}/windows/${windowId}`)
}

function closeDetail() {
  detail.value = null
}

const openLateTodo = computed(() =>
  detail.value?.todos.some((t) => t['待办类型'] === '迟到裁决' && t['状态'] === '待处理'),
)

async function backToWindow(row: SampleRow) {
  const payload = await getJson<{ items: WindowRow[] }>(
    `${ENDPOINT}/windows?keyword=${encodeURIComponent(String(row['指标编号']))}&size=200`,
  )
  const target = payload.items.find((w) => w['时间窗'] === row['时间窗'])
  if (!target) {
    actionOk.value = false
    actionMessage.value = '该样本所属联合窗口尚未建立'
    return
  }
  await openDetail(target.id)
}

async function postAction(path: string, body?: Record<string, unknown>) {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body ?? {}) })
  const payload = await response.json()
  actionOk.value = Boolean(payload.ok)
  actionMessage.value = String(payload.message ?? '')
  if (!payload.ok) return
  await reloadStats()
  if (detail.value) await openDetail(detail.value.window.id)
  if (activeTab.value === 'windows') await reloadWindows()
  if (activeTab.value === 'todos') await reloadTodos()
}

function publish(windowId: number) {
  void postAction(`${ENDPOINT}/windows/${windowId}/publish`)
}

function retest(windowId: number) {
  void postAction(`${ENDPOINT}/windows/${windowId}/retest`)
}

function arbitrate(windowId: number, choice: string) {
  void postAction(`${ENDPOINT}/windows/${windowId}/arbitrate`, { values: { choice } })
}

function resetSampleForm() {
  Object.keys(sampleForm).forEach((key) => {
    sampleForm[key] = key === '指标类型' ? '成功率' : ''
  })
}

async function submitSample() {
  const values: Record<string, string | number> = {}
  Object.entries(sampleForm).forEach(([key, value]) => {
    if (value !== '') values[key] = value
  })
  try {
    const response = await request(`${ENDPOINT}/samples`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    actionOk.value = Boolean(payload.ok)
    actionMessage.value = String(payload.message ?? '')
    if (payload.ok) {
      resetSampleForm()
      await reloadStats()
      await reloadWindows(1)
      await reloadSamples(1)
    }
  } catch (error) {
    actionOk.value = false
    actionMessage.value = error instanceof Error ? error.message : '样本提交失败'
  }
}

function switchTab(tab: TabKey) {
  activeTab.value = tab
  if (tab === 'todos') void reloadTodos()
  if (tab === 'samples') void reloadSamples()
  if (tab === 'windows') void reloadWindows()
}

onMounted(() => {
  void reloadStats()
  void reloadWindows(1)
})

// 内联分页组件：与列表接口的 page/size/total 口径保持一致。
const Pagination = defineComponent({
  name: 'Pagination',
  props: {
    page: { type: Number, required: true },
    size: { type: Number, required: true },
    total: { type: Number, required: true },
  },
  emits: ['change'],
  setup(props, { emit }) {
    const pageCount = () => Math.max(1, Math.ceil(props.total / props.size))
    return () =>
      h('footer', { class: 'pagination' }, [
        h('span', { class: 'page-desc' }, `共 ${props.total} 条，第 ${props.page} / ${pageCount()} 页`),
        h('button', {
          class: 'btn',
          disabled: props.page <= 1,
          onClick: () => emit('change', props.page - 1),
        }, '上一页'),
        h('button', {
          class: 'btn',
          disabled: props.page >= pageCount(),
          onClick: () => emit('change', props.page + 1),
        }, '下一页'),
      ])
  },
})
</script>

<style scoped>
.tab-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.tab-item { border: 1px solid var(--border); background: #fff; border-radius: 6px; padding: 6px 14px; cursor: pointer; font-size: 13px; }
.tab-item.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.conclusion-tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.tag-ok { background: #e7f6ec; color: #067647; }
.tag-bad { background: #fef3f2; color: #b42318; }
.tag-mid { background: #fffaeb; color: #b54708; }
.priority-tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.row-abnormal { background: #fffbfa; }
.row-inactive { opacity: 0.72; }
.late-tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; background: #fffaeb; color: #b54708; }
.endpoint-flag { color: #b42318; font-weight: 600; }
.summary-cell { max-width: 320px; font-size: 12px; color: #475467; }
.conflict-cell { color: #b42318; font-size: 12px; }
.pagination { display: flex; gap: 10px; align-items: center; margin-top: 10px; }
.ingest-form { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.form-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 12px 0; }
.form-actions { display: flex; gap: 10px; }
.check-item { display: flex; align-items: center; gap: 6px; }
.drawer-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45); display: flex; justify-content: flex-end; z-index: 50; }
.drawer { width: 72%; max-width: 980px; background: #f9fafb; height: 100%; overflow-y: auto; padding: 18px 22px; }
.drawer-head { display: flex; justify-content: space-between; align-items: center; }
.detail-block { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-bottom: 14px; }
.detail-block h4 { margin: 0 0 10px; font-size: 14px; }
.detail-actions { display: flex; gap: 10px; margin-top: 12px; }
.version-card { border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; background: #fcfcfd; }
.version-head { display: flex; gap: 12px; align-items: center; }
.ok-text { color: #067647; }
</style>
