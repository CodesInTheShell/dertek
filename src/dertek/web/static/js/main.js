import { useDertekStore } from './stores.js';
import { WorkspaceView, SessionView, SettingsView } from './components.js';

const router = VueRouter.createRouter({
  history: VueRouter.createWebHistory(),
  routes: [
    { path: '/', component: WorkspaceView },
    { path: '/sessions/:id', component: SessionView },
    { path: '/settings', component: SettingsView },
  ],
});

const App = {
  setup() {
    const store = useDertekStore();
    Vue.onMounted(async () => {
      try { await Promise.all([store.loadSessions(), store.resumeActiveRun()]); }
      catch (exc) { store.error = exc.message; }
    });
    return { store };
  },
  template: `
    <div class="app-shell d-flex">
      <aside class="app-sidebar p-3">
        <div class="d-flex align-items-center gap-2 mb-4"><span class="brand-mark">D</span><strong class="fs-5">Dertek</strong></div>
        <nav class="d-grid gap-1 mb-4">
          <router-link to="/" class="rounded p-2">New session</router-link>
          <router-link to="/settings" class="rounded p-2">Settings</router-link>
        </nav>
        <div class="small text-uppercase text-secondary fw-semibold mb-2">Sessions</div>
        <div class="sidebar-sessions">
          <router-link v-for="item in store.sessions" :key="item.id" :to="'/sessions/' + item.id" class="sidebar-session mb-1">
            <span class="d-block text-truncate">{{ item.preview || 'New session' }}</span>
            <small class="d-block text-truncate">{{ item.workspace }}</small>
          </router-link>
        </div>
      </aside>
      <main class="app-main flex-grow-1"><router-view></router-view></main>
    </div>`,
};

const app = Vue.createApp(App);
app.use(Pinia.createPinia());
app.use(router);
app.mount('#app');
