<template>
  <div v-if="data">
    <div class="card" style="display:flex;justify-content:space-between;align-items:center">
      <div>
        <button class="btn gray small" @click="$emit('back')">← 返回</button>
        <b style="font-size:18px;margin-left:10px">{{ data.project.title }}</b>
        <span class="badge" :class="data.project.status === 'done' ? 'ok' : data.project.status === 'failed' ? 'bad' : 'run'">{{ data.project.status }}</span>
        <span class="muted"> {{ data.project.style }} · {{ data.project.episodes }}集 × {{ data.project.shots_per_episode }}镜头</span>
      </div>
      <div>
        <button class="btn" :disabled="!scriptReady || producing" @click="produce">{{ producing ? '制作中…' : '🎥 开始制作' }}</button>
      </div>
    </div>

    <div class="tabs">
      <div class="tab" :class="{ active: tab === 'script' }" @click="tab = 'script'">📝 剧本</div>
      <div class="tab" :class="{ active: tab === 'assets' }" @click="tab = 'assets'">🎞 素材与进度</div>
      <div class="tab" :class="{ active: tab === 'final' }" @click="tab = 'final'">🎬 成片</div>
    </div>

    <!-- 剧本编辑 -->
    <div v-if="tab === 'script'">
      <div v-if="!script" class="card muted">剧本生成中，请稍候…（约1-2分钟）</div>
      <template v-else>
        <div class="card">
          <h2>角色卡</h2>
          <div>
            <div v-for="c in script.characters" :key="c.name" class="char-card">
              <img v-if="charImg(c.name)" :src="charImg(c.name)" />
              <div v-else style="width:150px;height:263px;line-height:263px;background:#12141d;border-radius:8px">未生成</div>
              <div class="name">{{ c.name }} <span class="muted">{{ c.voice }}</span></div>
              <div class="desc">{{ c.personality }}</div>
              <button class="btn small gray" style="margin-top:4px" @click="regenChar(c.name)">重绘定妆照</button>
            </div>
          </div>
        </div>

        <div class="card" v-for="ep in script.episodes" :key="ep.index">
          <h2>第 {{ ep.index }} 集 · {{ ep.summary }}</h2>
          <div class="shot" v-for="s in ep.shots" :key="s.shot_id">
            <div class="shot-head">
              <span class="shot-title">镜头 {{ s.shot_id }} · {{ s.camera }} · {{ s.scene }}</span>
            </div>
            <label>视频提示词（中文）</label>
            <textarea v-model="s.video_prompt" rows="2"></textarea>
            <label>首帧绘图提示词（英文）</label>
            <textarea v-model="s.first_frame_prompt" rows="2"></textarea>
            <label>台词</label>
            <div v-for="(d, i) in s.dialogue" :key="i" class="dlg">
              <select v-model="d.character" style="flex:0.8">
                <option v-for="c in script.characters" :key="c.name" :value="c.name">{{ c.name }}</option>
              </select>
              <input v-model="d.line" placeholder="台词" />
              <input v-model="d.emotion" class="em" placeholder="情绪" />
              <button class="btn small gray" @click="s.dialogue.splice(i, 1)">删</button>
            </div>
            <button class="btn small gray" @click="s.dialogue.push({ character: script.characters[0].name, line: '', emotion: '平静' })">+ 加台词</button>
          </div>
        </div>

        <div style="margin-bottom:20px">
          <button class="btn green" @click="save" :disabled="saving">{{ saving ? '保存中…' : '💾 保存剧本' }}</button>
          <button class="btn gray" style="margin-left:8px" @click="regenScript">🔄 重新生成剧本</button>
          <span v-if="msg" class="muted" style="margin-left:10px">{{ msg }}</span>
        </div>
      </template>
    </div>

    <!-- 素材与进度 -->
    <div v-if="tab === 'assets'">
      <div class="card">
        <h2>镜头进度</h2>
        <div class="grid">
          <div v-for="cell in shotCells" :key="cell.key" class="cell">
            <div><b>{{ cell.label }}</b></div>
            <img v-if="cell.keyframe" :src="cell.keyframe" />
            <video v-if="cell.video" :src="cell.video" controls muted style="margin-top:4px"></video>
            <div class="st">
              <span class="badge" :class="badgeCls(cell.st.keyframe)">图</span>
              <span class="badge" :class="badgeCls(cell.st.video)">视</span>
              <span class="badge" :class="badgeCls(cell.st.audio)">音</span>
            </div>
            <div v-if="cell.progress" class="bar"><div :style="{ width: cell.progress + '%' }"></div></div>
            <div style="margin-top:6px">
              <button class="btn small gray" @click="regenShot(cell, 'keyframe')">重图</button>
              <button class="btn small gray" @click="regenShot(cell, 'video')">重视频</button>
              <button class="btn small gray" @click="regenShot(cell, 'audio')">重配音</button>
            </div>
          </div>
        </div>
      </div>
      <div class="card" v-if="logs.length">
        <h2>实时日志</h2>
        <div v-for="(l, i) in logs.slice(-30)" :key="i" class="muted" style="font-size:12px">{{ l }}</div>
      </div>
    </div>

    <!-- 成片 -->
    <div v-if="tab === 'final'">
      <div class="card" v-if="data.project.status === 'done'">
        <h2>🎬 完整成片</h2>
        <video class="player" :src="api.staticUrl(pid + '/final.mp4') + '?t=' + reloadTs" controls></video>
        <div style="margin-top:10px">
          <a :href="api.staticUrl(pid + '/final.mp4')" download><button class="btn">⬇ 下载成片</button></a>
        </div>
      </div>
      <div class="card" v-for="ep in episodeList" :key="ep">
        <h2>第 {{ ep }} 集</h2>
        <video class="player" :src="api.staticUrl(`${pid}/episode_${ep}.mp4`) + '?t=' + reloadTs" controls></video>
      </div>
      <div v-if="data.project.status !== 'done' && !episodeList.length" class="card muted">
        成片还未生成。请到「剧本」页确认剧本后点击「开始制作」。
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from './api'

const props = defineProps({ pid: String })
const emit = defineEmits(['back'])

const data = ref(null)
const tab = ref('script')
const saving = ref(false)
const msg = ref('')
const producing = ref(false)
const logs = ref([])
const reloadTs = ref(0)
const liveProgress = ref({})
let ws = null, timer = null

const script = computed(() => data.value?.script)
const scriptReady = computed(() => !!script.value)
const episodeList = computed(() => (script.value?.episodes || []).map(e => e.index))

const shotCells = computed(() => {
  if (!script.value) return []
  const st = script.value._status?.shots || {}
  const cells = []
  for (const ep of script.value.episodes) {
    for (const s of ep.shots) {
      const key = `e${ep.index}_s${s.shot_id}`
      const stat = st[key] || {}
      cells.push({
        key, ep: ep.index, shot: s.shot_id,
        label: `E${ep.index}-S${s.shot_id} ${s.scene || ''}`,
        st: stat,
        keyframe: stat.keyframe === 'done' ? api.staticUrl(`${props.pid}/keyframes/${key}.png`) + '?t=' + reloadTs.value : null,
        video: stat.video === 'done' ? api.staticUrl(`video_clips/${props.pid}_${key}.mp4`) + '?t=' + reloadTs.value : null,
        progress: liveProgress.value[key] || null,
      })
    }
  }
  return cells
})

function charImg(name) {
  if (script.value?._status?.characters?.[name] !== 'done') return null
  return api.staticUrl(`${props.pid}/characters/${encodeURIComponent(name)}.png`) + '?t=' + reloadTs.value
}
function badgeCls(s) { return s === 'done' ? 'ok' : s === 'failed' ? 'bad' : 'info' }

async function load() {
  data.value = await api.getProject(props.pid)
  producing.value = data.value.project.status === 'running'
}
async function save() {
  saving.value = true; msg.value = ''
  try {
    const s = JSON.parse(JSON.stringify(script.value)); delete s._status
    await api.saveScript(props.pid, s)
    msg.value = '已保存'
  } catch (e) { msg.value = '保存失败: ' + e.message }
  saving.value = false
}
async function produce() {
  await save()
  await api.produce(props.pid)
  producing.value = true
  tab.value = 'assets'
}
async function regenScript() { await api.regenScript(props.pid) }
async function regenChar(name) { await api.regenCharacter(props.pid, name); reloadTs.value = Date.now() }
async function regenShot(cell, stage) {
  try { await api.regenShot(props.pid, cell.ep, cell.shot, stage); reloadTs.value = Date.now(); await load() }
  catch (e) { logs.value.push(`重生成失败 ${cell.key} ${stage}: ${e.message}`) }
}

function connectWs() {
  ws = new WebSocket(api.wsUrl(props.pid))
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data)
    const t = new Date().toLocaleTimeString()
    if (m.type === 'shot') {
      logs.value.push(`${t} 镜头${m.shot} ${m.stage}: ${m.status}${m.step ? ` ${m.step}/${m.total}` : ''}`)
      if (m.step) liveProgress.value[m.shot] = Math.round(m.step / m.total * 100)
      if (m.status === 'done') { liveProgress.value[m.shot] = null; reloadTs.value = Date.now(); load() }
    } else if (m.type === 'character') {
      logs.value.push(`${t} 角色${m.name}: ${m.status}`)
      reloadTs.value = Date.now(); load()
    } else if (m.type === 'stage') {
      logs.value.push(`${t} 阶段 ${m.stage}: ${m.status}${m.error ? ' ' + m.error : ''}`)
    } else if (m.type === 'project') {
      logs.value.push(`${t} 项目: ${m.status}${m.error ? ' ' + m.error : ''}`)
      producing.value = false
      reloadTs.value = Date.now(); load()
      if (m.status === 'done') tab.value = 'final'
    }
  }
  ws.onclose = () => setTimeout(connectWs, 3000)
}

onMounted(async () => { await load(); connectWs(); timer = setInterval(load, 15000) })
onUnmounted(() => { ws?.close(); clearInterval(timer) })
</script>
