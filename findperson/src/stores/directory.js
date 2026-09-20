import { defineStore } from "pinia";
import {
  STORAGE_KEYS,
  currentUserId,
  getActiveUserId,
  departmentHierarchyMap,
  loadJson,
  normalize,
  normalizePersonRecord,
  saveJson,
  splitTags,
} from "../state.js";
import {
  createDepartment as createServerDepartment,
  createPerson as createServerPerson,
  fetchDepartmentTree,
  fetchPeople,
  flattenDepartmentTree,
  updateDepartment as updateServerDepartment,
  updateDepartmentResponsibility as updateServerDepartmentResponsibility,
  updatePerson as updateServerPerson,
} from "../services/api/people.js";
import { getMockDepartments, getMockPeople, getMockRoles, saveMockDepartments, saveMockPeople, saveMockRoles } from "../services/mock/mockApi.js";
import { isServerMode } from "../services/mode.js";

const ALL_DEPARTMENTS = "";
// 名片库按姓名拼音(首字母)排序;Intl.Collator 的 zh 排序规则即拼音序
const pinyinCollator = new Intl.Collator("zh-Hans-CN");

export const useDirectoryStore = defineStore("directory", {
  state: () => ({
    people: getMockPeople(),
    departments: getMockDepartments(),
    roles: getMockRoles(),
    activeUserId: getActiveUserId(),
    loaded: false,
    keyword: "",
    filters: { departmentIds: [] },
  }),
  getters: {
    currentUser: (state) => state.people.find((person) => person.id === state.activeUserId),
    activePeople: (state) => state.people.filter((person) => person.active !== false),
    currentUserDepartment: (state) => state.departments.find((department) => department.name === state.people.find((person) => person.id === state.activeUserId)?.department),
    rootDepartments: (state) => state.departments.filter((department) => !department.parentId),
    departmentTree(state) {
      const nodes = new Map(state.departments.map((department) => [department.id, { ...department, children: [] }]));
      const roots = [];
      nodes.forEach((node) => {
        const parent = nodes.get(node.parentId);
        if (parent) parent.children.push(node);
        else roots.push(node);
      });
      return roots;
    },
    departmentFilterLevels() {
      const levels = [];
      let parentId = ALL_DEPARTMENTS;
      let index = 0;
      while (true) {
        const options = parentId
          ? this.departments.filter((department) => department.parentId === parentId)
          : this.rootDepartments;
        if (!options.length) break;
        const selectedId = this.filters.departmentIds[index] || ALL_DEPARTMENTS;
        levels.push({ index, options, selectedId, placeholder: index ? "全部下级部门" : "全部部门" });
        if (!selectedId) break;
        parentId = selectedId;
        index += 1;
      }
      return levels;
    },
    selectedDepartmentId: (state) => state.filters.departmentIds.filter(Boolean).at(-1) || "",
    filteredPeople() {
      const keyword = normalize(this.keyword);
      const selectedId = this.selectedDepartmentId;
      return this.people.filter((person) => {
        const haystack = normalize([
          person.name, person.department, person.role, person.domains.join(" "), person.selfPortrait,
        ].join(" "));
        return (!keyword || haystack.includes(keyword))
          && (!selectedId || this.isDepartmentOrDescendant(person.department, selectedId));
      }).sort((a, b) => pinyinCollator.compare(a.name || "", b.name || ""));
    },
  },
  actions: {
    async loadPeople() {
      // 已加载过就直接复用(含 server 模式):路由守卫每次导航都会调用,重复全量拉取会导致切换卡顿
      if (this.loaded) return;
      if (isServerMode()) {
        try {
          const [people, tree] = await Promise.all([
            fetchPeople({ page_size: 500 }),
            fetchDepartmentTree(),
          ]);
          this.departments = flattenDepartmentTree(tree);
          this.people = (people || []).map((person) => normalizePersonRecord(person));
        } catch (error) {
          console.warn("组织数据加载失败，已回退到演示数据", error);
          this.people = getMockPeople();
          this.departments = getMockDepartments();
        }
      } else {
        this.people = getMockPeople();
        this.departments = getMockDepartments();
      }
      this.roles = getMockRoles();
      this.people.forEach((person) => this.syncPersonDepartmentPath(person));
      this.loaded = true;
    },
    getPerson(personId) { return this.people.find((person) => person.id === personId); },
    getDepartment(reference) {
      return this.departments.find((item) => item.id === reference || item.name === reference);
    },
    childrenOf(departmentId) { return this.departments.filter((item) => item.parentId === departmentId); },
    isDepartmentOrDescendant(departmentRef, ancestorId) {
      let department = this.getDepartment(departmentRef);
      while (department) {
        if (department.id === ancestorId) return true;
        department = department.parentId ? this.getDepartment(department.parentId) : null;
      }
      return false;
    },
    managedDepartments(personId) {
      return this.departments.filter((department) => department.leaderId === personId);
    },
    manageableDepartments(personId) {
      const managedIds = this.managedDepartments(personId).map((department) => department.id);
      return this.departments.filter((department) => managedIds.some((id) => this.isDepartmentOrDescendant(department.id, id)));
    },
    isDepartmentLeader(personId, departmentRef) {
      return this.getDepartment(departmentRef)?.leaderId === personId;
    },
    getPersonSupervisor(personId) {
      const person = this.getPerson(personId);
      // 优先直接上级字段(manager_id,验收#7);缺省再沿部门负责人向上推导
      const direct = this.getPerson(person?.managerId);
      if (direct && direct.id !== personId) {
        return { person: direct, department: this.getDepartment(direct.department) };
      }
      let department = this.getDepartment(person?.department);
      while (department) {
        const supervisor = this.getPerson(department.leaderId);
        if (supervisor && supervisor.id !== personId) return { person: supervisor, department };
        department = department.parentId ? this.getDepartment(department.parentId) : null;
      }
      return null;
    },
    setCurrentUser(personId) { this.activeUserId = personId; },
    setDepartmentFilter(level, departmentId) {
      this.filters.departmentIds.splice(level, this.filters.departmentIds.length - level, departmentId || ALL_DEPARTMENTS);
    },
    setDepartmentFilterFromNode(department) {
      const path = [];
      let current = this.getDepartment(department?.id);
      while (current) {
        path.unshift(current.id);
        current = current.parentId ? this.getDepartment(current.parentId) : null;
      }
      this.filters.departmentIds = path;
    },
    resetDepartmentFilters() { this.filters.departmentIds = []; },
    departmentText(person) { return person?.departmentPath?.join(" / ") || person?.department || ""; },
    syncPersonDepartmentPath(person) {
      const department = this.getDepartment(person.department);
      person.departmentPath = department?.path?.slice() || departmentHierarchyMap[person.department] || person.departmentPath;
      return person;
    },
    updatePerson(personId, patch) {
      const person = this.getPerson(personId);
      if (!person) return null;
      const next = { ...patch };
      if (next.domainsText !== undefined) { next.domains = splitTags(next.domainsText); delete next.domainsText; }
      if (next.addDomains) { next.domains = Array.from(new Set([...(person.domains || []), ...next.addDomains])); delete next.addDomains; }
      if (next.removeDomains) { const rm = new Set(next.removeDomains); next.domains = (person.domains || []).filter((d) => !rm.has(d)); delete next.removeDomains; }
      Object.assign(person, next);
      this.syncPersonDepartmentPath(person);
      if (personId === getActiveUserId()) {
        const profiles = loadJson(STORAGE_KEYS.profile, {});
        saveJson(STORAGE_KEYS.profile, { ...(profiles?.id ? {} : profiles), [personId]: person });
      }
      if (!isServerMode()) saveMockPeople(this.people);
      return person;
    },
    /**
     * 管理员保存成员（server 模式调后端 /people，mock 模式走本地 store）
     */
    async savePerson(personId, patch) {
      const dept = this.getDepartment(patch.department);
      const payload = {
        name: patch.name,
        departmentId: dept?.id,
        role: patch.role,
        systemRole: patch.systemRole,
        active: patch.active,
      };
      if (patch.contact !== undefined) payload.contact = patch.contact;
      if (patch.phone !== undefined) payload.phone = patch.phone;
      if (patch.managerId !== undefined) payload.managerId = patch.managerId;

      if (!isServerMode()) {
        return personId ? this.updatePerson(personId, patch) : this.addPerson(patch);
      }

      try {
        const saved = personId
          ? await updateServerPerson(personId, payload)
          : await createServerPerson(payload);
        const normalized = this.syncPersonDepartmentPath(normalizePersonRecord(saved));
        if (personId) {
          const idx = this.people.findIndex((p) => p.id === personId);
          if (idx >= 0) this.people[idx] = normalized;
          else this.people.push(normalized);
        } else {
          this.people.push(normalized);
        }
        return normalized;
      } catch (error) {
        console.warn("成员保存失败", error);
        throw error;
      }
    },
    updateDepartment(departmentId, patch) {
      const department = this.getDepartment(departmentId);
      if (!department) return null;
      Object.assign(department, patch);
      saveMockDepartments(this.departments);
      return department;
    },
    /** 部门负责人保存职责（仅负责人可写，权限在后端校验） */
    async saveDepartmentResponsibility(departmentId, responsibility) {
      const department = this.getDepartment(departmentId);
      if (!department) return null;
      if (isServerMode()) {
        try {
          const saved = await updateServerDepartmentResponsibility(departmentId, responsibility);
          department.responsibility = saved.responsibility || "";
          return department;
        } catch (error) {
          console.warn("部门职责保存失败", error);
          throw error;
        }
      }
      department.responsibility = responsibility || "";
      saveMockDepartments(this.departments);
      return department;
    },
    async assignDepartmentLeader(departmentId, leaderId) {
      if (isServerMode()) {
        try {
          const saved = await updateServerDepartment(departmentId, { leader_id: leaderId || null });
          const department = this.getDepartment(departmentId);
          if (department) department.leaderId = saved.leader_id || "";
          // 后端会级联更新该部门成员的 manager_id，刷新人员列表
          this.loaded = false;
          await this.loadPeople();
          return department;
        } catch (error) {
          console.warn("负责人变更失败", error);
          throw error;
        }
      }
      const department = this.getDepartment(departmentId);
      if (!department) return null;
      department.leaderId = leaderId || "";
      saveMockDepartments(this.departments);
      return department;
    },
    async addDepartment({ name, parentId = "", responsibility = "" }) {
      const cleanName = String(name || "").trim();
      const parent = parentId ? this.getDepartment(parentId) : null;
      if (!cleanName || (parentId && !parent) || this.childrenOf(parentId).some((item) => item.name === cleanName)) return null;

      if (isServerMode()) {
        try {
          const saved = await createServerDepartment({
            name: cleanName,
            parent_id: parent?.id ?? null,
            level: (parent?.path?.length || 0) + 1,
            leader_id: null,
            responsibility,
            sort_order: 0,
          });
          const department = {
            id: saved.id,
            name: saved.name,
            parentId: saved.parent_id ?? "",
            path: Array.isArray(saved.path) && saved.path.length ? saved.path : [...(parent?.path || []), cleanName],
            leaderId: saved.leader_id || "",
            responsibility: saved.responsibility || "",
          };
          this.departments.push(department);
          return department;
        } catch (error) {
          console.warn("部门创建失败", error);
          throw error;
        }
      }

      const department = {
        id: `dept-${Date.now()}`,
        name: cleanName,
        parentId,
        path: [...(parent?.path || []), cleanName],
        leaderId: "",
        responsibility,
      };
      this.departments.push(department);
      saveMockDepartments(this.departments);
      return department;
    },
    addPerson(payload) {
      const department = this.getDepartment(payload.department);
      if (!department || !payload.name?.trim()) return null;
      const person = normalizePersonRecord({
        id: `p-${Date.now()}`, name: payload.name.trim(), department: department.name,
        departmentPath: department.path.slice(), role: payload.role || "专员", contact: payload.contact || "",
        domains: [], selfPortrait: "", peerPortrait: "", completeness: 0, recommendedCount: 0,
        systemRole: payload.systemRole || "普通成员", active: payload.active !== false,
      });
      this.people.push(person);
      if (!isServerMode()) saveMockPeople(this.people);
      return person;
    },
    addRole(name) {
      const role = String(name || "").trim();
      if (!role || this.roles.includes(role)) return false;
      this.roles.push(role);
      saveMockRoles(this.roles);
      return true;
    },
    removeRole(name) {
      if (this.people.some((person) => person.role === name)) return false;
      this.roles = this.roles.filter((role) => role !== name);
      saveMockRoles(this.roles);
      return true;
    },
  },
});
