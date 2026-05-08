import { createRouter, createWebHistory } from 'vue-router'
import { fetchAgents } from '../api/agents'

const routes = [
  {
    path: '/ops-report-demo',
    name: 'ops-report-demo',
    component: () => import('../OpsReportDemo.vue'),
  },
  {
    path: '/',
    redirect: async () => {
      const saved = localStorage.getItem('last_agent_type')
      if (saved) return `/${saved}`
      try {
        const data = await fetchAgents()
        const defaultType = data.default_agent_type
        if (defaultType) return `/${defaultType}`
      } catch (e) {
        // ignore
      }
      const firstAgent = data?.agents?.[0]?.agent_type
      if (firstAgent) return `/${firstAgent}`
      return '/desk-agent'
    },
  },
  {
    path: '/:agentType/knowledge',
    name: 'agent-knowledge',
    component: () => import('../KnowledgePage.vue'),
    props: true,
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
