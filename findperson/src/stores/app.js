import { defineStore } from "pinia";

export const useAppStore = defineStore("app", {
  state: () => ({
    previousRoute: "",
    sourceRoute: "",
    globalError: "",
    globalLoading: false,
  }),
  actions: {
    rememberRoute(route) {
      if (route?.fullPath) this.previousRoute = route.fullPath;
    },
    setSourceRoute(route) {
      this.sourceRoute = route?.fullPath || route || "";
    },
    clearSourceRoute() {
      this.sourceRoute = "";
    },
  },
});
