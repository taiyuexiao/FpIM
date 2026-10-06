// ═══════════════════════════════════════════════════════════════════════════
// match.js — 首问必答平台 智能匹配逻辑层
// ═══════════════════════════════════════════════════════════════════════════
//
// 包含：问题分析、关键词抽取、意图推断、人员评分、内容匹配、
//       助手动作生成、回复文本生成、推荐标签、周活趋势
// ═══════════════════════════════════════════════════════════════════════════

import { normalize, splitTags, getTodayText } from "../state.js";

// ── 问题分析 ───────────────────────────────────────────────────────────────

/**
 * 分析用户问题，返回意图、领域、关键词和置信度
 * @param {string} question - 用户原始问题
 * @param {Object} domainDictionary - 领域词典
 * @returns {{ original, normalized, intent, domains, tokens, confidence }}
 */
export function analyzeQuestion(question, domainDictionary) {
  const normalized = normalize(question);
  const domains = Object.entries(domainDictionary)
    .filter(([, words]) => words.some((word) => normalized.includes(word.toLowerCase())))
    .map(([domain]) => domain);
  const tokens = extractTokens(normalized, domainDictionary);
  const intent = inferIntent(normalized);
  return {
    original: question,
    normalized,
    intent,
    domains: domains.length ? domains : ["待判断"],
    tokens: Array.from(new Set(tokens.concat(domains))).slice(0, 10),
    confidence: Math.min(95, 50 + domains.length * 12 + Math.min(tokens.length, 6) * 4),
  };
}

// ── 关键词抽取 ─────────────────────────────────────────────────────────────

/** 从归一化文本中抽取领域关键词和中文片段 */
export function extractTokens(normalized, domainDictionary) {
  const words = [];
  // 匹配领域词典中的关键词
  Object.values(domainDictionary).flat().forEach((word) => {
    const key = word.toLowerCase();
    if (normalized.includes(key)) words.push(word);
  });
  // 抽取 2-8 字中文片段
  const chineseChunks = normalized.match(/[一-龥]{2,}/g) || [];
  chineseChunks.forEach((chunk) => {
    if (chunk.length <= 8) words.push(chunk);
  });
  return words;
}

// ── 意图推断 ───────────────────────────────────────────────────────────────

/** 根据归一化文本推断用户意图 */
export function inferIntent(normalized) {
  if (/(登录|密码)/.test(normalized)) return "账号访问";
  if (/(操作手册|手册|怎么用)/.test(normalized)) return "平台使用";
  if (/(我要画像|画像一下|补充画像)/.test(normalized)) return "他人画像";
  if (/(我要发布|发布|发一篇|写一个|流程说明|常见问题)/.test(normalized)) return "内容发布";
  if (/(修改|更新|维护|改我的|联系方式|负责领域|自画像|个人信息)/.test(normalized)) return "信息维护";
  if (/(找谁|谁负责|问谁|联系谁)/.test(normalized)) return "问题找人";
  if (/(申请|开通|审批)/.test(normalized)) return "流程咨询";
  if (/(报错|异常|失败|不一致|排查)/.test(normalized)) return "问题排查";
  return "业务咨询";
}

// ── 助手动作生成 ───────────────────────────────────────────────────────────

/**
 * 根据问题分析结果生成助手待确认动作（资料维护 / 画像 / 内容发布）
 * @returns {{ type, title, description, changes?, nextProfilePatch?, nextReview?, nextContent? }}
 */
export function buildAssistantAction(
  question,
  analysis,
  matches,
  contentHits,
  { currentUserId, authName, peopleList }
) {
  const normalized = analysis.normalized;

  // ── 资料维护 ──
  if (/(修改|更新|改我的|联系方式|负责领域|自画像)/.test(normalized)) {
    const changes = [];
    const nextProfilePatch = {};

    // 提取手机号
    const phone = question.match(/1\d{10}/);
    if (phone) {
      nextProfilePatch.contact = phone[0];
      changes.push(`联系方式将更新为 ${phone[0]}`);
    }

    // 提取负责领域
    const domainMatch = question.match(
      /负责领域(?:增加|新增|添加|补充|改为)?\s*[:：]?\s*([^，。；\n]+)/
    );
    const nextDomains = domainMatch ? splitTags(domainMatch[1]) : [];
    if (nextDomains.length) {
      nextProfilePatch.addDomains = nextDomains;
      changes.push(`负责领域将增加 ${nextDomains.join("、")}`);
    } else if (/负责领域/.test(normalized)) {
      changes.push("负责领域会同步到个人主页与推荐匹配");
    }

    // 提取自画像
    const portraitMatch = question.match(
      /自画像(?:修改为|改为|更新为|补充为|写为|调整为)?\s*[:：]?\s*([^。；\n]+)/
    );
    const nextPortrait = portraitMatch?.[1]?.trim();
    if (nextPortrait && !/^我要修改我的自画像$/.test(nextPortrait)) {
      nextProfilePatch.selfPortrait = nextPortrait;
      changes.push("自画像将同步更新到个人主页与推荐匹配");
    } else if (/自画像/.test(normalized)) {
      changes.push("自画像内容会影响后续找人推荐");
    }

    return {
      type: "profile",
      title: "检测到资料维护需求",
      description: "我已识别到你要维护个人资料，可以直接确认更新或去个人中心手动编辑。",
      changes,
      nextProfilePatch,
    };
  }

  // ── 他人画像 ──
  if (/(我要画像|画像一下|补充画像)/.test(normalized)) {
    const person =
      matches[0]?.person || peopleList.find((item) => item.id !== currentUserId);
    return {
      type: "review",
      title: "已生成一条待确认画像",
      description: "我先根据你的表述生成了一条画像草稿，你确认后会写入对方主页。",
      nextReview: {
        id: `review-${Date.now()}`,
        personId: person.id,
        reviewer: authName,
        date: getTodayText(),
        tag: person.domains[0] || "协同响应",
      },
    };
  }

  // ── 内容发布 ──
  if (/(我要发布|发布|发一篇|写一个|流程说明|常见问题)/.test(normalized)) {
    const focusDomain =
      analysis.domains.find((item) => item !== "待判断") || "平台培训";
    return {
      type: "content",
      title: "已整理内容发布草稿",
      description: "我根据你的问题整理了一篇待发布内容，你可以直接确认，也可以继续补充正文。",
      nextContent: {
        id: `c-${Date.now()}`,
        ownerId: currentUserId,
        title: `${focusDomain}相关说明`,
        tags: [focusDomain, "首问必答平台"],
        summary: `围绕${focusDomain}整理办理步骤、常见卡点和咨询入口。`,
        body: "一、适用场景\n二、办理步骤\n三、常见问题与联系路径",
        publishedAt: getTodayText(),
        pinned: false,
        weeklyQueryCount: 18,
        weeklyRecommendCount: 11,
      },
    };
  }

  // ── 默认：人员推荐 ──
  return {
    type: "match",
    title: "已完成首问推荐",
    description: "我按照你当前问题匹配了相关负责人，建议优先联系首推对象。",
  };
}

// ── 内容匹配 ───────────────────────────────────────────────────────────────

/** 根据问题分析结果匹配相关内容，按置顶 → 命中分 → 发布时间排序 */
export function matchContent(analysis, contentList) {
  return contentList
    .flatMap((item) => item.status === "已发布" ? [item] : (item.publishedSnapshot ? [item.publishedSnapshot] : []))
    .map((item) => {
      const text = normalize(
        `${item.title} ${item.tags.join(" ")} ${item.summary} ${item.body || ""}`
      );
      let score = 0;
      analysis.domains.forEach((domain) => {
        if (domain !== "待判断" && item.tags.includes(domain)) score += 24;
        else if (domain !== "待判断" && text.includes(domain.toLowerCase())) score += 12;
      });
      analysis.tokens.forEach((token) => {
        if (text.includes(token.toLowerCase())) score += 5;
      });
      return { ...item, hitScore: score };
    })
    .filter((item) => item.hitScore > 0)
    .sort(
      (left, right) =>
        Number(right.pinned) - Number(left.pinned) ||
        right.hitScore - left.hitScore ||
        right.publishedAt.localeCompare(left.publishedAt)
    );
}

// ── 人员评分 ───────────────────────────────────────────────────────────────

/**
 * 对单个人员进行推荐评分
 * 综合考虑：负责领域、岗位职责、自画像、他画像、发布内容、推荐次数
 */
export function scorePerson(person, analysis, contentHits, contentList, reviewsForPersonFn) {
  const personContent = contentList
    .flatMap((item) => item.status === "已发布" ? [item] : (item.publishedSnapshot ? [item.publishedSnapshot] : []))
    .filter((item) => item.ownerId === person.id);
  const haystack = normalize(
    [
      person.name,
      person.department,
      person.role,
      person.domains.join(" "),
      person.selfPortrait,
      reviewsForPersonFn(person.id).map((item) => item.tag || item.text).join(" "),
      personContent.map((item) => `${item.title} ${item.summary}`).join(" "),
    ].join(" ")
  );

  let score = 24 + Math.round(person.recommendedCount / 12);
  const reasons = [];

  analysis.domains.forEach((domain) => {
    if (domain !== "待判断" && person.domains.includes(domain)) {
      score += 26;
      reasons.push(`负责领域包含"${domain}"`);
    } else if (domain !== "待判断" && haystack.includes(domain.toLowerCase())) {
      score += 12;
      reasons.push(`个人资料中命中"${domain}"`);
    }
  });

  analysis.tokens.forEach((token) => {
    if (haystack.includes(token.toLowerCase())) score += 4;
  });

  const related = contentHits.filter((item) => item.ownerId === person.id).slice(0, 2);
  if (related.length) {
    reasons.push(`关联内容 ${related.map((item) => item.title).join("、")}`);
  }

  return { person, score, reasons: reasons.slice(0, 3), related };
}

// ── 顶层编排：matchQuestion ─────────────────────────────────────────────────

/**
 * 处理用户问题的顶层入口
 * 1. 分析问题意图和关键词
 * 2. 匹配相关内容
 * 3. 对所有人员评分并排序
 * 4. 生成助手动作
 * @returns {{ analysis, action, matches, contentHits }}
 */
export function matchQuestion(
  question,
  peopleList,
  contentList,
  reviewsForPersonFn,
  currentUserId,
  authName,
  domainDictionary
) {
  const analysis = analyzeQuestion(question, domainDictionary);
  const contentHits = matchContent(analysis, contentList).slice(0, 5);
  const matches = peopleList
    .map((person) =>
      scorePerson(person, analysis, contentHits, contentList, reviewsForPersonFn)
    )
    .sort((left, right) => right.score - left.score)
    .slice(0, 3);
  const action = buildAssistantAction(question, analysis, matches, contentHits, {
    currentUserId,
    authName,
    peopleList,
  });
  return { analysis, action, matches, contentHits };
}

// ── 助手回复文本 ───────────────────────────────────────────────────────────

/** 根据匹配结果生成助手回复的简短文本 */
export function getAssistantReply(result) {
  const primary = result.matches?.[0]?.person;
  const firstContent = result.contentHits?.[0];

  if (result.action.type === "profile") return result.action.description;
  if (result.action.type === "review") return "好的，我为你整理了一条画像草稿，请确认。";
  if (result.action.type === "content") return result.action.description;
  if (primary) return "好的，下面为你推荐相关负责人。";
  return "目前还没有找到足够明确的对象，建议补充系统名、流程名或材料名。";
}

// ── 推荐标签 ───────────────────────────────────────────────────────────────

/** 根据推荐位置返回标签：首推 / 可协助 / 相关人员 */
export function getRecommendationLabel(index) {
  if (index === 0) return "首推";
  if (index === 1) return "可协助";
  return "相关人员";
}

// ── 周活趋势数据 ───────────────────────────────────────────────────────────

/**
 * 构建后台管理页的周日活趋势数据
 * @param {number} offset - 0 表示本周，1 表示上周
 * @returns {Array<{ day: string, value: number, percent: number }>}
 */
export function buildWeeklyActiveTrend(offset) {
  const base = offset
    ? [42, 48, 39, 54, 61, 45, 36]
    : [58, 63, 71, 69, 82, 77, 64];
  const days = offset
    ? ["上周一", "上周二", "上周三", "上周四", "上周五", "上周六", "上周日"]
    : ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  const max = Math.max(...base);
  return base.map((value, index) => ({
    day: days[index],
    value,
    percent: Math.round((value / max) * 100),
  }));
}
