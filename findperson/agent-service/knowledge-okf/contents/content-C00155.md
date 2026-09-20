---
type: contents
id: content-C00155
title: 反洗钱报送的应用心得
version: 2
status: published
visibility: internal
sensitivity: 0
source_type: public.contents
source_id: C00155
source_uri: public.contents/C00155
owner_department_id: 18
updated_at: 1789519086.642175
content_hash: e5eb55054380ce756f566f4c48595990aeba1315c74010480bcee513decdb392
extra:
  author_person_id: P0104
  tags:
  - 平台应用开发
  - 应用开发组
---

反洗钱报送的应用心得

数据应用的可扩展性，要从设计之初就考虑。业务会不断变化，新的指标、新的场景会持续涌现。若应用结构僵硬，每加一个功能都要大动干戈，迭代成本就会越来越高。因此要用配置化、组件化的思路，让常见的扩展通过配置即可完成，而不是每次都要改代码。同时要预留好数据模型与接口的扩展点，避免早期设计堵死后续演进的路。可扩展性不是过度设计，而是用合理的抽象，为未来的变化留出余地，让应用能随业务一起成长。用户体验的细节，往往才是决定产品成败的分水岭。

主题:平台应用开发、应用开发组

作者:张顺
