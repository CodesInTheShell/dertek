import { useDertekStore } from './stores.js';

const { computed, onMounted, ref, watch } = Vue;

export const WorkspaceView = {
  setup() {
    const store = useDertekStore();
    const router = VueRouter.useRouter();
    const path = ref('');
    const busy = ref(false);
    const error = ref('');
    onMounted(async () => {
      try {
        await store.browse();
        path.value = store.workspace.path;
        await store.loadSessions();
      } catch (exc) { error.value = exc.message; }
    });
    async function browse(next) {
      try {
        error.value = '';
        await store.browse(next);
        path.value = store.workspace.path;
      } catch (exc) { error.value = exc.message; }
    }
    async function create() {
      busy.value = true;
      error.value = '';
      try {
        const id = await store.createSession(path.value);
        await router.push(`/sessions/${id}`);
      } catch (exc) { error.value = exc.message; }
      finally { busy.value = false; }
    }
    return { store, path, busy, error, browse, create };
  },
  template: `
    <div class="container-fluid py-4 px-lg-5">
      <h1 class="h3 mb-2">Choose a workspace</h1>
      <p class="text-secondary">Dertek runs tools inside the folder you choose.</p>
      <div class="card shadow-sm mb-4"><div class="card-body">
        <label class="form-label fw-semibold" for="workspace-path">Project folder</label>
        <div class="input-group mb-3">
          <input id="workspace-path" v-model="path" class="form-control" aria-label="Project folder path" @keyup.enter="browse(path)">
          <button class="btn btn-outline-secondary" @click="browse(path)">Browse</button>
        </div>
        <div v-if="store.workspace" class="workspace-list border rounded mb-3">
          <button class="workspace-item list-group-item list-group-item-action w-100 text-start border-0" @click="browse(store.workspace.parent)">⬆ Parent folder</button>
          <button v-for="dir in store.workspace.directories" :key="dir.path" class="workspace-item list-group-item list-group-item-action w-100 text-start border-0" @click="browse(dir.path)">📁 {{ dir.name }}</button>
          <div v-if="!store.workspace.directories.length" class="p-3 text-secondary">No subfolders here.</div>
        </div>
        <div v-if="error" class="alert alert-danger">{{ error }}</div>
        <button class="btn btn-primary" :disabled="busy" @click="create">Start session in this folder</button>
      </div></div>
      <h2 class="h5">Recent sessions</h2>
      <div class="list-group shadow-sm">
        <router-link v-for="item in store.sessions" :key="item.id" :to="'/sessions/' + item.id" class="list-group-item list-group-item-action">
          <div class="fw-semibold">{{ item.preview || 'New session' }}</div>
          <small class="text-secondary">{{ item.workspace }} · {{ item.turns }} turns</small>
        </router-link>
        <div v-if="!store.sessions.length" class="list-group-item text-secondary">No sessions yet.</div>
      </div>
    </div>`,
};

export const SessionView = {
  setup() {
    const store = useDertekStore();
    const route = VueRouter.useRoute();
    const prompt = ref('');
    const loading = ref(false);
    const error = ref('');
    const currentId = computed(() => route.params.id);
    async function load() {
      loading.value = true;
      error.value = '';
      try { await store.loadSession(currentId.value); }
      catch (exc) { error.value = exc.message; }
      finally { loading.value = false; }
    }
    onMounted(load);
    watch(currentId, load);
    async function submit() {
      if (!prompt.value.trim()) return;
      const text = prompt.value;
      try {
        await store.startRun(text);
        prompt.value = '';
      } catch (exc) { error.value = exc.message; }
    }
    async function approve(allowed) {
      try { await store.answerApproval(allowed); }
      catch (exc) { error.value = exc.message; }
    }
    async function reset() {
      try { await store.resetContext(); }
      catch (exc) { error.value = exc.message; }
    }
    function summary(event) {
      const data = event.data || {};
      if (event.type === 'route') return `${event.message} · ${data.model || ''} · ${data.reasoning_effort || ''}`;
      if (event.type === 'tool_started') return `Tool: ${event.message}`;
      if (event.type === 'model_escalated') return event.message;
      return event.message;
    }
    return { store, prompt, loading, error, submit, approve, reset, summary, currentId };
  },
  template: `
    <div class="container-fluid py-4 px-lg-5" v-if="store.session && store.session.id === currentId">
      <div class="d-flex align-items-start justify-content-between gap-3 mb-4">
        <div><h1 class="h3 mb-1">Conversation</h1><div class="text-secondary small">{{ store.session.workspace }}</div></div>
        <button class="btn btn-sm btn-outline-secondary" :disabled="store.running" @click="reset">Reset model context</button>
      </div>
      <div v-if="store.contextWillRestart" class="alert alert-info">Saved conversation is visible. ChatGPT model context will restart on the next prompt.</div>
      <div v-if="store.notice" class="alert alert-info">{{ store.notice }}</div>
      <div v-if="error || store.error" class="alert alert-danger">{{ error || store.error }}</div>
      <div v-for="(turn, index) in store.session.history" :key="index" class="mb-4">
        <div class="small text-secondary text-end mb-1">You</div>
        <div class="chat-bubble chat-user mb-3">{{ turn.prompt }}</div>
        <div class="small text-secondary mb-1">Dertek <span v-if="turn.model">· {{ turn.model }}</span></div>
        <div class="chat-bubble chat-assistant">{{ turn.response || turn.error || 'No final response saved.' }}</div>
        <details v-if="turn.tools && turn.tools.length" class="mt-2">
          <summary class="small text-secondary">{{ turn.tools.length }} tool calls</summary>
          <div v-for="tool in turn.tools" :key="tool.call_id" class="event-line small">
            <strong>{{ tool.name }}</strong> <span v-if="tool.is_error" class="text-danger">· error</span>
            <pre class="code-detail mb-1">{{ JSON.stringify(tool.arguments, null, 2) }}</pre>
            <pre v-if="tool.output" class="code-detail text-secondary mb-0">{{ tool.output }}</pre>
          </div>
        </details>
      </div>
      <details v-if="store.activeSessionId === currentId && (store.running || store.events.length)" class="card shadow-sm mb-4">
        <summary class="card-body fw-semibold">Current run <span v-if="store.running" class="spinner-border spinner-border-sm ms-2" aria-label="Running"></span></summary>
        <div class="card-body pt-0">
          <div v-for="event in store.events" :key="event.event_id" class="event-line small" :class="{ error: event.type === 'error' || event.type === 'run_error', approval: event.type === 'approval_request' }">{{ summary(event) }}</div>
        </div>
      </details>
      <div v-if="store.activeSessionId === currentId && store.approval" class="card border-warning shadow-sm mb-4"><div class="card-body">
        <h2 class="h5">Approval required: {{ store.approval.tool }}</h2>
        <p class="small text-secondary">{{ store.approval.reason }}</p>
        <pre class="code-detail bg-light p-3 rounded">{{ JSON.stringify(store.approval.arguments, null, 2) }}</pre>
        <div class="d-flex gap-2">
          <button class="btn btn-success" @click="approve(true)">Approve</button>
          <button class="btn btn-outline-danger" @click="approve(false)">Deny</button>
        </div>
        <div class="small text-secondary mt-2">Unanswered requests are denied after five minutes.</div>
      </div></div>
      <form class="card shadow-sm" @submit.prevent="submit"><div class="card-body">
        <label for="prompt" class="form-label fw-semibold">Ask Dertek</label>
        <textarea id="prompt" v-model="prompt" class="form-control mb-3" rows="4" placeholder="Describe a task in this workspace" :disabled="store.running"></textarea>
        <button class="btn btn-primary" :disabled="store.running || !prompt.trim()">Send</button>
      </div></form>
    </div>
    <div v-else class="container-fluid py-5 px-lg-5">
      <div v-if="loading" class="text-secondary">Loading session…</div>
      <div v-else-if="error" class="alert alert-danger">{{ error }}</div>
    </div>`,
};

export const SettingsView = {
  setup() {
    const store = useDertekStore();
    const form = ref({});
    const original = ref({});
    const busy = ref(false);
    const error = ref('');
    const fields = [
      ['small_model', 'Small model', 'text'],
      ['large_model', 'Large model', 'text'],
      ['router_high_confidence', 'High confidence threshold', 'number'],
      ['router_medium_confidence', 'Medium confidence threshold', 'number'],
      ['max_steps', 'Maximum agent steps', 'number'],
      ['max_jev_calls_per_turn', 'Maximum Jev calls per turn', 'number'],
      ['small_model_step_limit', 'Small model step limit', 'number'],
      ['shell_timeout_seconds', 'Shell timeout (seconds)', 'number'],
    ];
    onMounted(async () => {
      try {
        await store.loadSettings();
        form.value = { ...store.settings.effective, ...store.settings.saved };
        original.value = { ...form.value };
      } catch (exc) { error.value = exc.message; }
    });
    async function save() {
      busy.value = true;
      error.value = '';
      try {
        const changes = Object.fromEntries(Object.entries(form.value).filter(([key, value]) => value !== original.value[key]));
        if (Object.keys(changes).length) await store.saveSettings(changes);
        else store.notice = 'No settings changed.';
        form.value = { ...store.settings.effective, ...store.settings.saved };
        original.value = { ...form.value };
      } catch (exc) { error.value = exc.message; }
      finally { busy.value = false; }
    }
    return { store, form, busy, error, fields, save };
  },
  template: `
    <div class="container-fluid py-4 px-lg-5">
      <h1 class="h3 mb-2">Settings</h1>
      <p class="text-secondary">Saved values apply to new runs. Environment variables may override them.</p>
      <div v-if="store.notice" class="alert alert-success">{{ store.notice }}</div>
      <div v-if="error" class="alert alert-danger">{{ error }}</div>
      <form v-if="store.settings" class="card shadow-sm mb-4" @submit.prevent="save"><div class="card-body">
        <div class="settings-grid">
          <div v-for="field in fields" :key="field[0]">
            <label class="form-label fw-semibold" :for="field[0]">{{ field[1] }}</label>
            <input :id="field[0]" v-model.number="form[field[0]]" :type="field[2]" class="form-control" :step="field[0].includes('confidence') ? 0.01 : 1">
          </div>
          <div><label class="form-label fw-semibold" for="small-effort">Small reasoning effort</label>
            <select id="small-effort" v-model="form.small_reasoning_effort" class="form-select"><option v-for="effort in ['none','low','medium','high','xhigh','max']">{{ effort }}</option></select></div>
          <div><label class="form-label fw-semibold" for="large-effort">Large reasoning effort</label>
            <select id="large-effort" v-model="form.large_reasoning_effort" class="form-select"><option v-for="effort in ['none','low','medium','high','xhigh','max']">{{ effort }}</option></select></div>
          <div><label class="form-label fw-semibold" for="auth-mode">OpenAI authentication</label>
            <select id="auth-mode" v-model="form.openai_auth" class="form-select"><option value="api-key">API key</option><option value="chatgpt">ChatGPT</option></select></div>
          <div><label class="form-label fw-semibold" for="approval-mode">Approval mode</label>
            <select id="approval-mode" v-model="form.approval_mode" class="form-select"><option value="on-request">On request</option><option value="never">Never</option><option value="auto">Auto</option></select></div>
          <div class="d-flex align-items-end"><div class="form-check mb-2">
            <input id="jev-verification" v-model="form.jev_verification_enabled" type="checkbox" class="form-check-input">
            <label for="jev-verification" class="form-check-label">Jev final verification</label>
          </div></div>
        </div>
        <button class="btn btn-primary mt-4" :disabled="busy">Save settings</button>
      </div></form>
      <div v-if="store.auth" class="card shadow-sm"><div class="card-body">
        <h2 class="h5">Authentication status</h2>
        <div>ChatGPT: {{ store.auth.chatgpt_signed_in ? 'Signed in' : 'Not signed in' }}</div>
        <div>OpenAI API key: {{ store.auth.api_key_present ? 'Available' : 'Missing' }}</div>
        <div>TypeSafe Jev key: {{ store.auth.jev_key_present ? 'Available' : 'Missing; heuristic routing applies' }}</div>
        <p class="small text-secondary mt-3 mb-0">To sign in with ChatGPT, run <code>dertek auth login</code> in a terminal. API keys are supplied through environment variables, never this page.</p>
      </div></div>
    </div>`,
};
