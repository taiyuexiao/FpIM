export function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

export function splitTags(value) {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  return String(value || "").split(/[、,，\s]+/).map((item) => item.trim()).filter(Boolean);
}
