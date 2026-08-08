<template>
  <div>
    <div class="header">
      <h1>🎬 AI 短剧平台</h1>
      <div class="svc">
        <span v-for="(ok, name) in health" :key="name" class="badge" :class="ok ? 'ok' : 'bad'">{{ svcNames[name] || name }}</span>
      </div>
    </div>

    <!-- 首页 -->
    <div v-if="!pid">
      <div class="card">
        <h2>✨ 新建短剧</h2>
        <label>小说 / 故事梗概</label>
        <textarea v-model="form.synopsis" rows="4" placeholder="例如：外卖员林晓暴雨夜送最后一单，意外救下被追杀的千金小姐，从此卷入豪门恩怨……"></textarea>
        <div class="row">
          <div>
            <label>风格</label>
            <select v-model="form.style">
              <option v-for="s in styles" :key="s">{{ s }}</option>
            </select>
          </div>
          <div>
            <label>集数</label>
            <input type="number" v-model.number="form.episodes" min="1" max="10" />
          </div>
          <div>
            <label>每集镜头数</label>
            <input type="number" v-model.number="form.shots_per_episode" min="2" max="12" />
          </div>
          <div>
            <label>模式</label>
            <select v-model="form.auto_produce">
              <option :value="false">剧本后人工确认</option>
              <option :value="true">全自动一键出片</option>
            </select>
          </div>
        </div>
        <div style="margin-top:12px">
          <button class="btn green" :disabled="creating || !form.synopsis" @click="create">
            {{ creating ? '创建中…' : '🚀 生成剧本' }}
          </button>
        </div>
        <div v-if="error" class="err">{{ error }}</div>
      </div>

      <div class="card">
        <h2>📁 项目列表</h2>
        <div v-if="!projects.length" class="muted">暂无项目</div>
        <div v-for="p in projects" :key="p.id" class="proj-item" @click="open(p.id)">
          <div>
            <div>{{ p.title || '未命名' }}</div>
            <div class="muted">{{ p.synopsis.slice(0, 40) }}… · {{ p.style }} · {{ p.episodes }}集</div>
          </div>
          <span class="badge" :class="statusClass(p.status)">{{ statusText(p.status) }} / {{ stageText(p.stage) }}</span>
        </div>
      </div>
    </div>

    <!-- 项目详情 -->
    <Project v-else :pid="pid" @back="pid = null; load()" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from './api'
import Project from './Project.vue'

const pid = ref(null)
const projects = ref([])
const health = ref({})
const creating = ref(false)
const error = ref('')
const styles = ['都市', '古风', '悬疑', '科幻', '写实', '动漫']
const svcNames = { llm: '剧本', comfy: '绘图', video: '视频', tts: '配音' }
const form = ref({ synopsis: '', style: '都市', episodes: 1, shots_per_episode: 6, auto_produce: false })

function statusText(s) {
  return { created: '已创建', running: '进行中', script_done: '剧本完成', done: '已完成', failed: '失败' }[s] || s
}
function stageText(s) {
  return { script: '剧本', characters: '角色', keyframes: '分镜', audios: '配音', videos: '视频', assembling: '合成', done: '完成' }[s] || s || ''
}
function statusClass(s) {
  return s === 'done' ? 'ok' : s === 'failed' ? 'bad' : s === 'running' ? 'run' : 'info'
}
async function load() {
  projects.value = (await api.listProjects()).projects
}
async function create() {
  creating.value = true; error.value = ''
  try {
    const r = await api.createProject(form.value)
    pid.value = r.project_id
  } catch (e) { error.value = e.message }
  creating.value = false
}
function open(id) { pid.value = id }

onMounted(async () => {
  await load()
  try { health.value = await api.health() } catch (e) {}
  setInterval(async () => { try { health.value = await api.health() } catch (e) {} }, 30000)
})
</script>
