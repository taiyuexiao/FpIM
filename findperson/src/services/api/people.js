import http from "./http.js";

export const fetchPeople = (params) => http.get("/people", { params });
export const fetchPerson = (id) => http.get(`/people/${id}`);
export const fetchDepartmentTree = () => http.get("/departments/tree");
export const createPerson = (payload) => http.post("/people", payload);
export const updatePerson = (id, payload) => http.patch(`/people/${id}`, payload);
export const createDepartment = (payload) => http.post("/departments", payload);
export const updateDepartment = (id, payload) => http.patch(`/departments/${id}`, payload);
export const updateDepartmentResponsibility = (id, responsibility) => http.patch(`/departments/${id}/responsibility`, { responsibility });

/** 后端部门树 → 前端平铺结构({id,name,parentId,leaderId,path,responsibility}) */
export function flattenDepartmentTree(nodes, parentPath = [], parentId = "") {
  const out = [];
  for (const node of nodes || []) {
    const path = [...parentPath, node.name];
    out.push({
      id: node.id,
      name: node.name,
      parentId: node.parent_id ?? parentId ?? "",
      leaderId: node.leader_id || "",
      path,
      responsibility: node.responsibility || "",
      memberCount: node.member_count || 0,
    });
    out.push(...flattenDepartmentTree(node.children, path, node.id));
  }
  return out;
}

/** 个人数据画像（被问/解决/帮助榜排名/知识沉淀/首响时长） */
export const fetchProfileStats = (id) => http.get(`/people/${id}/profile-stats`);
