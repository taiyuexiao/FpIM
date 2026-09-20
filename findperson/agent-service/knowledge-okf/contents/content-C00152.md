---
type: contents
id: content-C00152
title: 反洗钱报送的经验与总结
version: 2
status: published
visibility: internal
sensitivity: 0
source_type: public.contents
source_id: C00152
source_uri: public.contents/C00152
owner_department_id: 18
updated_at: 1789519086.533542
content_hash: 927f07bb4560e27b1fb66f4fbfa7ef522292c2a14411b039805b4e006abcf9db
extra:
  author_person_id: P0102
  tags:
  - 平台应用开发
  - 应用开发组
---

反洗钱报送的经验与总结

数据应用与数据仓库的分工要清晰。应用层负责呈现与交互，数仓层负责加工与口径，二者职责不同却紧密衔接。若应用层直接对接原始表，口径散落、维护困难；若把所有逻辑都堆进数仓，又会让数仓臃肿。合理的做法是在数仓沉淀统一口径，在应用层做面向场景的轻量加工。这样既保证了口径的一致，又保留了应用的灵活性。清晰的分工，是数据应用体系可维护、可演进的前提，也能让两边的团队各司其职、各展所长。迭代的意义，在于每一次都比上一次更贴近用户的真实需要。

主题:平台应用开发、应用开发组

作者:嵇雅娟
