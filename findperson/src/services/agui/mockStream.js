import { domainDictionary } from "../../state.js";
import { getAssistantReply, matchQuestion } from "../../utils/match.js";

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function* createMockAguiStream({
  sessionId,
  runId,
  messageId,
  question,
  people,
  content,
  reviewsForPerson,
  currentUserId,
  authName,
}) {
  const result = matchQuestion(
    question,
    people,
    content,
    reviewsForPerson,
    currentUserId,
    authName,
    domainDictionary
  );
  const reply = getAssistantReply(result);
  yield { type: "run_started", sessionId, runId, messageId, result };
  for (const chunk of chunkText(reply)) {
    await delay(45);
    yield { type: "text_delta", sessionId, runId, messageId, delta: chunk };
  }
  yield { type: "text_finished", sessionId, runId, messageId };
  if (result.action.type === "match") {
    await delay(120);
    yield {
      type: "recommendation_cards",
      sessionId,
      runId,
      messageId,
      cards: result.matches.map((match, index) => ({
        id: `rec-${messageId}-${match.person.id}`,
        kind: "recommendation",
        rank: index + 1,
        rankLabel: index === 0 ? "首推" : index === 1 ? "可协助" : "相关人员",
        person: match.person,
        personId: match.person.id,
        reasons: match.reasons,
        related: match.related,
      })),
    };
  } else {
    await delay(120);
    yield {
      type: "confirmation_card",
      sessionId,
      runId,
      messageId,
      card: {
        id: `confirm-${messageId}`,
        kind: "confirmation",
        action: result.action,
        analysis: result.analysis,
        status: "active",
      },
    };
  }
  yield {
    type: "state_delta",
    sessionId,
    runId,
    patch: {
      title: question.slice(0, 28),
      turnCountIncrement: 1,
      summary: `${question} ${result.analysis.intent}`,
    },
  };
  yield { type: "run_finished", sessionId, runId, messageId };
}

function chunkText(text) {
  const chunks = [];
  for (let index = 0; index < text.length; index += 4) {
    chunks.push(text.slice(index, index + 4));
  }
  return chunks.length ? chunks : [""];
}

export async function* createMockEventStream(events = []) {
  for (const event of events) {
    yield event;
  }
}
