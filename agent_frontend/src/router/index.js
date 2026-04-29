import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: () => {
      const saved = localStorage.getItem('last_agent_type')
      return saved || '/desk-agent'
    },
  },
  {
    path: '/:agentType',
    name: 'agent',
    component: () => import('../AgentLayout.vue'),
    props: true,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  const agentType = to.params.agentType
  if (agentType) {
    localStorage.setItem('last_agent_type', agentType)
  }
})

export default router
