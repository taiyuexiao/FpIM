export function normalizeAguiEvent(event) {
  const typeMap = {
    message_start: "run_started",
    message_delta: "text_delta",
    message_end: "text_finished",
    card_recommendation: "recommendation_cards",
    card_confirmation: "confirmation_card",
    session_patch: "state_delta",
    error: "run_error",
    done: "run_finished",
  };
  const data = event.data || event.payload || {};
  return {
    ...event,
    ...data,
    type: event.type || typeMap[event.event] || event.event,
    cards: event.cards || data.cards,
    card: event.card || data.card,
    delta: event.delta ?? data.delta ?? data.text,
    patch: event.patch || data.patch,
    message: event.message || data.message,
  };
}
