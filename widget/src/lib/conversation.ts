// Conversation id persists per-tenant so a visitor's chat survives a page
// reload (same iframe origin, namespaced by widget key so multiple tenants'
// demo widgets on one preview page never collide).

function storageKey(widgetKey: string): string {
  return `hf_conversation_id_${widgetKey}`
}

export function loadConversationId(widgetKey: string): string | null {
  try {
    return localStorage.getItem(storageKey(widgetKey))
  } catch {
    return null
  }
}

export function saveConversationId(widgetKey: string, conversationId: string): void {
  try {
    localStorage.setItem(storageKey(widgetKey), conversationId)
  } catch {
    // localStorage unavailable (e.g. strict privacy mode) — conversation just
    // won't survive a reload; the chat itself still works for this session.
  }
}
