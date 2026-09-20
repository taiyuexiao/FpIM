import { defineStore } from "pinia";
import { fetchActivityTrend, fetchAdminMetrics, fetchRecommendRanking } from "../services/api/admin.js";
import { isServerMode } from "../services/mode.js";
import { buildWeeklyActiveTrend } from "../utils/match.js";
import { useContentStore } from "./content.js";
import { useDirectoryStore } from "./directory.js";

export const useAdminStore = defineStore("admin", {
  state: () => ({
    activeWeek: 0,
    serverMetrics: null,
    serverRanking: null,
    serverTrend: null,
  }),
  getters: {
    metrics() {
      if (this.serverMetrics) return this.serverMetrics;
      const directory = useDirectoryStore();
      const content = useContentStore();
      const domains = new Set(directory.activePeople.flatMap((person) => person.domains));
      const weeklyRecommendationTotal = directory.activePeople.reduce((total, person) => total + person.recommendedCount, 0);
      return {
        peopleCount: directory.activePeople.length,
        contentCount: content.contents.length,
        domainCount: domains.size,
        weeklyRecommendationTotal,
      };
    },
    ranking() {
      if (this.serverRanking) return this.serverRanking;
      return useDirectoryStore().activePeople
        .map((person) => ({ person, value: person.recommendedCount }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 5);
    },
    trend() {
      if (this.serverTrend) return this.serverTrend;
      return buildWeeklyActiveTrend(this.activeWeek);
    },
    trendTotal() {
      return this.trend.reduce((total, item) => total + item.value, 0);
    },
  },
  actions: {
    async loadAdminData() {
      if (!isServerMode()) return;
      const [metrics, ranking, trend] = await Promise.all([
        fetchAdminMetrics(),
        fetchRecommendRanking(),
        fetchActivityTrend({ week: this.activeWeek ? "previous" : "current" }),
      ]);
      this.serverMetrics = metrics;
      this.serverRanking = ranking;
      this.serverTrend = trend;
    },
  },
});
