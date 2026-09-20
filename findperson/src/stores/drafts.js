import { defineStore } from "pinia";
import { loadJson, saveJson, STORAGE_KEYS } from "../state.js";

export const useDraftsStore = defineStore("drafts", {
  state: () => ({
    records: loadJson(STORAGE_KEYS.drafts, {}),
  }),
  actions: {
    persist() {
      saveJson(STORAGE_KEYS.drafts, this.records);
    },
    create(type, payload, source = "") {
      const id = `draft-${type}-${Date.now()}`;
      this.records[id] = {
        id,
        type,
        payload: JSON.parse(JSON.stringify(payload || {})),
        source,
        updatedAt: new Date().toISOString(),
      };
      this.persist();
      return id;
    },
    get(id, type = "") {
      const record = this.records[id];
      return record && (!type || record.type === type) ? record : null;
    },
    remove(id) {
      if (!id || !this.records[id]) return;
      delete this.records[id];
      this.persist();
    },
  },
});
