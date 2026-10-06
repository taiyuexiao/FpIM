---
type: contents
id: content-C00147
title: 数据门户的建设实践
version: 2
status: published
visibility: internal
sensitivity: 0
source_type: public.contents
source_id: C00147
source_uri: public.contents/C00147
owner_department_id: 18
updated_at: 1789519086.354018
content_hash: b183536ec2554c975ef701c59f926ca7b62919b0533312688ba0a5ce90decfc4
extra:
  author_person_id: P0099
  tags:
  - 平台应用开发
  - 应用开发组
---

数据门户的建设实践

数据应用的性能问题多数出在查询与数据量上。优化要从源头入手：合理建模、避免全表扫描、善用索引与预计算，而不是等到报表变慢才临时救火。性能优化的最佳时机，是在数据规模还小的时候就养成好习惯。优化时要先定位瓶颈所在，是查询写法不合理、缺少索引，还是数据量本身过大，再对症下药。同时要建立性能的监控与预警，让性能问题在恶化之前就被发现。性能不是一次性的优化，而是贯穿应用生命周期的一项持续工作，需要长期投入与关注。把复杂留给系统，把简单留给用户，这是数据产品设计的初心。

主题:平台应用开发、应用开发组

作者:李敏吉
