export function getTodayText() {
  return new Date().toISOString().slice(0, 10);
}
