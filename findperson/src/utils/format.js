export function formatDepartmentPath(person) {
  return person?.departmentPath?.join(" / ") || person?.department || "";
}
