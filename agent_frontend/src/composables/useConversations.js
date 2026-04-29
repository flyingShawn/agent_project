import { ref, computed } from 'vue'
import {
  getConversations as fetchConversations,
  getConversation as fetchConversation,
  updateConversationTitle,
  deleteConversation as deleteConversationApi,
} from '../api/conversations'

const conversations = ref([])
const currentConversationId = ref(null)

const currentTitle = computed(() => {
  const conv = conversations.value.find((c) => c.id === currentConversationId.value)
  return conv?.title || '新对话'
})

export function useConversations() {
  async function loadConversations(userId = 'admin', agentType = 'desk-agent') {
    try {
      const data = await fetchConversations(agentType, userId)
      conversations.value = data.items || []
    } catch (e) {
      console.error('[useConversations] 加载会话列表失败:', e)
    }
  }

  async function switchConversation(agentType, id) {
    try {
      const data = await fetchConversation(agentType, id)
      currentConversationId.value = id
      return data
    } catch (e) {
      console.error('[useConversations] 切换会话失败:', e)
      return null
    }
  }

  async function renameConversation(agentType, id, title) {
    try {
      const result = await updateConversationTitle(agentType, id, title)
      if (result.success) {
        const conv = conversations.value.find((c) => c.id === id)
        if (conv) {
          conv.title = result.title
        }
      }
      return result
    } catch (e) {
      console.error('[useConversations] 重命名失败:', e)
      return { success: false }
    }
  }

  async function removeConversation(agentType, id) {
    try {
      const result = await deleteConversationApi(agentType, id)
      if (result.success) {
        conversations.value = conversations.value.filter((c) => c.id !== id)
        if (currentConversationId.value === id) {
          currentConversationId.value = null
        }
      }
      return result
    } catch (e) {
      console.error('[useConversations] 删除会话失败:', e)
      return { success: false }
    }
  }

  function startNewConversation() {
    currentConversationId.value = null
  }

  function updateConversationInList(conversationId, title) {
    const conv = conversations.value.find((c) => c.id === conversationId)
    if (conv) {
      conv.title = title
    }
  }

  return {
    conversations,
    currentConversationId,
    currentTitle,
    loadConversations,
    switchConversation,
    renameConversation,
    removeConversation,
    startNewConversation,
    updateConversationInList,
  }
}
