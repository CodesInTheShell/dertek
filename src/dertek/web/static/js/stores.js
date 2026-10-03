import { api } from './api.js';

export const useDertekStore = Pinia.defineStore('dertek', {
  state: () => ({
    sessions: [],
    session: null,
    contextWillRestart: false,
    workspace: null,
    settings: null,
    auth: null,
    events: [],
    activeRunId: null,
    activeSessionId: null,
    running: false,
    approval: null,
    error: '',
    notice: '',
    eventSource: null,
  }),
  actions: {
    async loadSessions() {
      const data = await api('/api/sessions');
      this.sessions = data.sessions;
    },
    async loadSession(id) {
      const data = await api(`/api/sessions/${encodeURIComponent(id)}`);
      this.session = data.session;
      this.contextWillRestart = data.context_will_restart;
    },
    async browse(path) {
      const query = path ? `?path=${encodeURIComponent(path)}` : '';
      this.workspace = await api(`/api/workspaces${query}`);
    },
    async createSession(path) {
      const data = await api('/api/sessions', { method: 'POST', body: { workspace: path } });
      await this.loadSessions();
      this.session = data.session;
      this.contextWillRestart = false;
      return data.session.id;
    },
    async startRun(prompt) {
      if (!this.session || this.running) return;
      this.error = '';
      this.notice = '';
      this.events = [];
      this.approval = null;
      const id = this.session.id;
      const data = await api(`/api/sessions/${id}/runs`, {
        method: 'POST', body: { prompt },
      });
      this.connectRun(data.run_id, id);
    },
    async resumeActiveRun() {
      const data = await api('/api/runs/active');
      if (data.run_id && !this.activeRunId) this.connectRun(data.run_id, data.session_id);
    },
    connectRun(runId, sessionId) {
      this.activeRunId = runId;
      this.activeSessionId = sessionId;
      this.running = true;
      this.events = [];
      this.approval = null;
      if (this.eventSource) this.eventSource.close();
      const source = new EventSource(`/api/runs/${runId}/events`);
      this.eventSource = source;
      source.onmessage = async (message) => {
        const event = JSON.parse(message.data);
        this.events.push(event);
        if (event.type === 'approval_request') this.approval = event.data;
        if (['approval_timeout', 'approval_resolved'].includes(event.type)) this.approval = null;
        if (event.type === 'context_restarted') this.notice = event.message;
        if (event.type === 'run_result' || event.type === 'run_error') {
          source.close();
          this.eventSource = null;
          this.running = false;
          this.activeRunId = null;
          this.approval = null;
          if (event.type === 'run_error') this.error = event.message;
          if (this.session?.id === sessionId) await this.loadSession(sessionId);
          await this.loadSessions();
        }
      };
      source.onerror = async () => {
        if (!this.running) return;
        this.notice = 'Connection interrupted; trying to reconnect.';
        try {
          const current = await api('/api/runs/active');
          if (current.run_id !== runId) {
            source.close();
            this.eventSource = null;
            this.running = false;
            this.activeRunId = null;
            this.approval = null;
            this.error = 'The web server restarted or this run ended before the browser received its result.';
            await this.loadSessions();
          }
        } catch (_) {
          // The server may be temporarily unavailable; EventSource will retry.
        }
      };
    },
    async answerApproval(approved) {
      if (!this.approval || !this.activeRunId) return;
      const approvalId = this.approval.approval_id;
      await api(`/api/runs/${this.activeRunId}/approvals/${approvalId}`, {
        method: 'POST', body: { approved },
      });
      this.approval = null;
    },
    async resetContext() {
      if (!this.session) return;
      const data = await api(`/api/sessions/${this.session.id}/reset`, { method: 'POST' });
      this.session = data.session;
      this.contextWillRestart = false;
      this.notice = 'Model context reset.';
    },
    async loadSettings() {
      this.settings = await api('/api/settings');
      this.auth = await api('/api/auth/status');
    },
    async saveSettings(values) {
      this.settings = await api('/api/settings', { method: 'PUT', body: { values } });
      await this.loadSettings();
      this.notice = 'Settings saved. New runs will use these settings.';
    },
  },
});
