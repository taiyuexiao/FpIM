> ⚠️ **本文件是原项目（findperson）的遗留文档，2026-09-17 迁入时发现已损坏。**
>
> - 原文件为 **UTF-16 编码**（git 视作二进制、无法 diff），已转为 UTF-8。
> - 其中文内容在更早的某个环节被**按 GBK 误解码**，已**不可完整还原**（含私有区字符，无法逆向）。
> - 文件内的明文口令已替换为占位符。
>
> **现行文档以仓库根 `docs/` 为准**（见 `docs/PROJECT.md`）。

# 棣栭棶璐ｄ换骞冲彴 鈥?鍚庣 API

> 鍒嗘敮锛歚backend` | FastAPI + PostgreSQL 17 + pgvector | 2026-08-14

鍚庣鏈嶅姟 + 鏁版嵁搴撹縼绉?+ 涓?Agent / RAG 鐨勫鎺ユ敹鍙ｃ€傚綋鍓?*鍓嶇鐩磋繛 Agent**锛屽悗绔?`/api/agui/*` 閫€鍖栦负銆孉gent 鏈帴鍏ユ椂鐨勯檷绾у厹搴曘€嶃€?
---

## 蹇€熷紑濮?
```bash
# 1. 鐜鍙橀噺
cp .env.example .env
# 缂栬緫 .env锛屽～鍏ュ疄闄呮暟鎹簱瀵嗙爜鍜?JWT 瀵嗛挜

# 2. 瀹夎渚濊禆
pip install -r requirements.txt

# 3. 鍚姩鏁版嵁搴擄紙PostgreSQL 17 + pgvector锛?docker compose up -d

# 4. 鏁版嵁搴撹縼绉?alembic upgrade head

# 5. 绉嶅瓙鏁版嵁
cat scripts/seed.sql | docker exec -i swzr-pg psql -U swzr_admin -d shouwenzeren

# 6. 鍚姩鍚庣
uvicorn app.main:app --port 8000
```

鍚姩鍚庤闂細
- **Swagger 鏂囨。**锛歚http://localhost:8000/docs`
- **ReDoc**锛歚http://localhost:8000/redoc`
- **鍋ュ悍妫€鏌?*锛歚http://localhost:8000/health`

娴嬭瘯璐﹀彿锛歚p0001` ~ `p0300`锛屽瘑鐮佺粺涓€ `<种子账号口令，见 .env>`銆傜鐞嗗憳锛歚p0001`锛坄system_role=绠＄悊鍛榒锛夈€?
---

## 椤圭洰缁撴瀯

```
backend/
鈹溾攢鈹€ app/
鈹?  鈹溾攢鈹€ main.py              # FastAPI 鍏ュ彛锛屾敞鍐岃矾鐢?+ CORS + 涓棿浠?+ lifespan(瀹氭椂浠诲姟)
鈹?  鈹溾攢鈹€ api/
鈹?  鈹?  鈹溾攢鈹€ v1/              # 涓氬姟璺敱灞傦紙/api/v1锛?鈹?  鈹?  鈹?  鈹溾攢鈹€ auth.py      # 鐧诲綍 / 娉ㄥ唽 / 鏀瑰瘑
鈹?  鈹?  鈹?  鈹溾攢鈹€ me.py        # 褰撳墠鐢ㄦ埛 / 鏇存柊璧勬枡 / 鏀瑰瘑锛圥UT /me/password锛?鈹?  鈹?  鈹?  鈹溾攢鈹€ people.py    # 浜哄憳鍚嶇墖 CRUD
鈹?  鈹?  鈹?  鈹溾攢鈹€ contents.py  # 鍐呭 CRUD + 鎻愪氦瀹℃牳 + 瀹℃牳 + 缃《
鈹?  鈹?  鈹?  鈹溾攢鈹€ reviews.py   # 浠栫敾鍍忥紙鏍囩锛?鈹?  鈹?  鈹?  鈹溾攢鈹€ admin.py     # 绠＄悊鐪嬫澘 / 缁熻 / 瀹¤鏃ュ織
鈹?  鈹?  鈹?  鈹溾攢鈹€ departments.py # 閮ㄩ棬
鈹?  鈹?  鈹?  鈹斺攢鈹€ sessions.py  # 浼氳瘽 CRUD + 娑堟伅鍒楄〃
鈹?  鈹?  鈹斺攢鈹€ agui/            # AGUI 鏀跺彛璺敱灞傦紙/api/agui锛?鈹?  鈹?      鈹溾攢鈹€ sessions.py  # 寤轰細璇?/ 浼氳瘽鐘舵€佸揩鐓?鈹?  鈹?      鈹溾攢鈹€ messages.py  # SSE 娴佸紡闂瓟锛圓gent 鏈帴鍏ユ椂闄嶇骇锛?鈹?  鈹?      鈹溾攢鈹€ events.py    # 鍙嶉 / 浜や簰浜嬩欢涓婃姤
鈹?  鈹?      鈹斺攢鈹€ schemas.py   # AGUI 璇锋眰浣?鈹?  鈹溾攢鈹€ models/              # SQLAlchemy ORM
鈹?  鈹?  鈹溾攢鈹€ user.py          # 鐢ㄦ埛
鈹?  鈹?  鈹溾攢鈹€ department.py    # 閮ㄩ棬
鈹?  鈹?  鈹溾攢鈹€ content.py       # 鍐呭锛堝惈 audit_trail jsonb锛?鈹?  鈹?  鈹溾攢鈹€ review.py        # 鏍囩锛圥eerReview锛?鈹?  鈹?  鈹溾攢鈹€ session.py       # 浼氳瘽 / 娑堟伅 / 鏌ヨ鏃ュ織锛圦ueryLog锛?鈹?  鈹?  鈹溾攢鈹€ assistant.py     # 鎺ㄨ崘鏃ュ織 / 鍙嶉锛坮ecommendation_logs / feedback锛?鈹?  鈹?  鈹斺攢鈹€ admin.py         # 缁熻鍙ｅ緞 / 缁熻缁撴灉 / 瀹¤鏃ュ織
鈹?  鈹溾攢鈹€ schemas/             # Pydantic 璇锋眰/鍝嶅簲妯″瀷
鈹?  鈹溾攢鈹€ core/                # 閰嶇疆 / 鏁版嵁搴?/ 瀹夊叏
鈹?  鈹?  鈹溾攢鈹€ config.py        # 鐜鍙橀噺锛堝惈 AGENT_BASE_URL锛?鈹?  鈹?  鈹溾攢鈹€ scheduler.py     # lifespan 瀹氭椂鍒锋柊缁熻锛堟瘡灏忔椂锛?鈹?  鈹?  鈹斺攢鈹€ statistics.py    # 缁熻鍙ｅ緞鍒锋柊锛圫ELECT-only formula锛?鈹?  鈹溾攢鈹€ middleware/          # 涓棿浠?鈹?  鈹?  鈹溾攢鈹€ auth.py          # JWT 閴存潈 鈫?request.state.user_id / user_role
鈹?  鈹?  鈹溾攢鈹€ audit.py         # 鎿嶄綔瀹¤钀藉簱锛坅udit_logs锛?鈹?  鈹?  鈹斺攢鈹€ deps.py          # get_current_user / require_admin / get_role_type
鈹?  鈹斺攢鈹€ services/
鈹?      鈹溾攢鈹€ agent_client.py  # Agent 瀵规帴濂戠害锛堝綋鍓嶅墠绔洿杩烇紝鍚庣浠呭厹搴曪級
鈹?      鈹斺攢鈹€ publish_event.py # 鍐呭鍙戝竷/鍙樻洿浜嬩欢 鈫?rag.publish_events
鈹溾攢鈹€ tests/                   # pytest锛?2 鐢ㄤ緥锛?鈹溾攢鈹€ requirements.txt
鈹斺攢鈹€ .env.example

alembic/                      # 鏁版嵁搴撹縼绉?鈹溾攢鈹€ versions/
鈹?  鈹溾攢鈹€ 64c9fe23ca1b_initial_baseline.py
鈹?  鈹溾攢鈹€ c1d2e3f4a5b6_p3_admin_tables.py
鈹?  鈹溾攢鈹€ f1a2b3c4d5e6_p5_publish_events.py
鈹?  鈹斺攢鈹€ a7b3c9d1e2f4_agent_compat_views.py
schema.sql                   # 鍏ㄩ噺 DDL 鍙傝€?docker-compose.yml           # PostgreSQL 17 + pgvector锛坰wzr-pg锛?scripts/                     # 绉嶅瓙鏁版嵁鐢熸垚 / seed.sql
```

---

## API 绔偣娓呭崟

> 鍓嶇紑锛歚/api/v1`锛堜笟鍔★級銆乣/api/agui`锛堥棶绛旀敹鍙ｏ級 | Swagger `http://localhost:8000/docs` 鏈夊畬鏁磋姹?鍝嶅簲绀轰緥

### 璁よ瘉

| 鏂规硶 | 璺緞 | 璇存槑 |
|------|------|------|
| POST | `/auth/login` | 鐧诲綍锛岃繑鍥?`{ token, user }` |
| POST | `/auth/register` | 绠＄悊鍛樺垱寤虹敤鎴?|
| POST | `/auth/change-password` | 淇敼瀵嗙爜锛堟棫鐗堬級 |
| PUT | `/me/password` | 淇敼鑷繁鐨勫瘑鐮侊紙楠屾棫鏀规柊锛屽墠绔綋鍓嶄娇鐢級 |

### 褰撳墠鐢ㄦ埛

| 鏂规硶 | 璺緞 | 璇存槑 |
|------|------|------|
| GET | `/me` | 褰撳墠鐢ㄦ埛淇℃伅 |
| PUT | `/me/profile` | 鏇存柊涓汉璧勬枡 |

### 浜哄憳

| 鏂规硶 | 璺緞 | 璇存槑 |
|------|------|------|
| GET | `/people` | 浜哄憳鍒楄〃锛坘eyword / department_id / domain 绛涢€夛級 |
| GET | `/people/{id}` | 浜哄憳璇︽儏 |
| PATCH | `/people/{id}` | 鏇存柊浜哄憳淇℃伅 |
| GET | `/people/{id}/reviews` | 鏌愪汉鏍囩鍘嗗彶锛堝垎椤碉級 |

### 鍐呭

| 鏂规硶 | 璺緞 | 璇存槑 |
|------|------|------|
| GET | `/contents` | 鍐呭鍒楄〃锛坰tatus / owner_id / pinned 绛涢€夛級 |
| POST | `/contents` | 鍒涘缓鍐呭锛坰tatus 鍙€夛紝"寰呭鏍? 鐩存帴杩涘鏍搁槦鍒楋級 |
| GET | `/contents/{id}` | 鍐呭璇︽儏 |
| PUT/PATCH | `/contents/{id}` | 缂栬緫鍐呭锛堜粎浣滆€?/ 绠＄悊鍛橈級 |
| DELETE | `/contents/{id}` | 杞垹闄わ紙浠呬綔鑰?/ 绠＄悊鍛橈級 |
| POST | `/contents/{id}/submit` | 鎻愪氦瀹℃牳锛?*浠呬綔鑰?*锛?|
| POST | `/contents/{id}/audit` | 瀹℃牳閫氳繃/椹冲洖锛?*浠呯鐞嗗憳**锛?|
| POST | `/contents/{id}/pin` | 鍒囨崲缃《锛?*浠呯鐞嗗憳**锛?|

### 浠栫敾鍍?
| 鏂规硶 | 璺緞 | 璇存槑 |
|------|------|------|
| POST | `/reviews` | 鎵撴爣绛?|
| GET | `/reviews/sent` | 鎴戝彂鍑虹殑鏍囩 |
| DELETE | `/reviews/{id}` | 鍒犻櫎鏍囩 |
| GET | `/reviews/person/{id}` | 鏌愪汉鏍囩姹囨€?|
| GET | `/reviews/person/{id}/history` | 鏌愪汉鏍囩鍘嗗彶锛堝垎椤碉級 |

### 绠＄悊鐪嬫澘锛堜粎绠＄悊鍛橈級

| 鏂规硶 | 璺緞 | 璇存槑 |
|------|------|------|
| GET | `/admin/dashboard` | 鐪嬫澘姒傝 |
| GET | `/admin/metrics` | 鏍稿績鎸囨爣锛堜汉鏁般€佸唴瀹规暟銆侀鍩熸暟銆佹湰鍛ㄦ帹鑽愶級 |
| GET | `/admin/rankings/recommend` | 鎺ㄨ崘鐑害 TOP10 |
| GET | `/admin/trends/activity` | 杩?7 澶╂椿鍔ㄨ秼鍔匡紙`?week=current\|previous`锛?|
| GET | `/admin/statistics` | 缁熻鎸囨爣鍒楄〃 |
| GET | `/admin/statistics/data` | 缁熻缁撴灉蹇収锛堝畾鏃跺埛鏂板啓鍏?`statistics_data`锛?|
| GET | `/admin/statistics/{key}` | 缁熻鎸囨爣瀹炴椂鍊?|
| GET | `/admin/audit-logs` | 鎿嶄綔瀹¤鏃ュ織锛堝垎椤碉級 |

### 閮ㄩ棬

| 鏂规硶 | 璺緞 | 璇存槑 |
|------|------|------|
| GET | `/departments/tree` | 閮ㄩ棬鏍戯紙鍚垚鍛樻暟锛?|
| GET | `/departments/{id}` | 閮ㄩ棬璇︽儏 |
| PATCH | `/departments/{id}` | 鏇存柊閮ㄩ棬 |
| POST | `/departments` | 鍒涘缓閮ㄩ棬 |

### 浼氳瘽

| 鏂规硶 | 璺緞 | 璇存槑 |
|------|------|------|
| GET | `/sessions` | 鎴戠殑浼氳瘽鍒楄〃 |
| POST | `/sessions` | 鏂板缓浼氳瘽锛堟帴鍙楀墠绔嚜甯?`id`锛屽箓绛夛級 |
| PATCH | `/sessions/{id}` | 鏇存柊浼氳瘽锛堥噸鍛藉悕 / 鎽樿 / 杞锛?|
| DELETE | `/sessions/{id}` | 杞垹闄や細璇?|
| GET | `/sessions/{id}/messages` | 鏌愪細璇濇秷鎭垪琛?|

### AGUI 鏀跺彛锛坄/api/agui`锛屽墠绔洿杩?Agent 鏃剁殑闄嶇骇鍏滃簳锛?
| 鏂规硶 | 璺緞 | 璇存槑 |
|------|------|------|
| POST | `/agui/sessions` | 鏂板缓闂瓟浼氳瘽 |
| GET | `/agui/sessions/{id}/state` | 浼氳瘽鐘舵€佸揩鐓?|
| POST | `/agui/sessions/{id}/messages` | 鍙戞秷鎭紙SSE 娴佸紡锛汚gent 鏈帴鍏ヨ繑鍥為檷绾ф彁绀猴級 |
| POST | `/agui/events` | 鍙嶉 / 浜や簰浜嬩欢涓婃姤锛坄feedback_toggle` 鈫?`feedback` 琛級 |

---

## 鏈鏂板鍔熻兘

### 1. 绠＄悊鍚庡彴涓庣粺璁?
- **缁熻鍙ｅ緞鍒锋柊**锛歚statistics_definitions`锛堝彛寰?SQL锛屼粎鍏佽 `SELECT`锛? `statistics_data`锛堢粨鏋滃揩鐓э級銆?  - `core/statistics.py`锛氶亶鍘嗗彛寰勬墽琛?formula锛岄€愭潯瀹归敊锛堝崟涓彛寰勫け璐ヤ笉闃诲锛夈€?  - `core/scheduler.py`锛欶astAPI `lifespan` 鍐?asyncio 寰幆锛屽惎鍔ㄦ椂绔嬪嵆鍒锋柊涓€娆★紝涔嬪悗姣忓皬鏃跺埛鏂帮紙涓嶅紩鍏?APScheduler锛岄伩鍏嶅 worker 閲嶅鎵ц锛夈€?- **鎿嶄綔瀹¤**锛歚audit_logs` 琛?+ `AuditMiddleware`锛岃嚜鍔ㄨ褰曠櫥褰曠敤鎴风殑 `POST/PUT/PATCH/DELETE` 鎿嶄綔锛坄/api/v1/auth/*`銆乣/health`銆乣/docs` 绛夎烦杩囷級銆?
### 2. 閴存潈涓庢潈闄愬姞鍥?
- `AuthMiddleware`锛氳В鏋?JWT 鈫?娉ㄥ叆 `request.state.user_id` / `user_role`銆?- `middleware/deps.py`锛歚get_current_user`锛?01 鏈櫥褰曪級銆乣require_admin`锛?03 闈炵鐞嗗憳锛夈€乣get_role_type`銆?- 鍐呭鎺ュ彛琛ラ綈褰掑睘/瑙掕壊鏍￠獙锛歚audit` / `pin` 浠呯鐞嗗憳锛宍submit` / `delete` 浠呬綔鑰咃紙鎴栫鐞嗗憳锛夈€?
### 3. 浼氳瘽 CRUD 琛ュ叏

- 鏂板 `POST /sessions`锛堝墠绔嚜甯?`id` 骞傜瓑鍒涘缓锛夈€乣PATCH /sessions/{id}`銆乣DELETE /sessions/{id}`锛堣蒋鍒犻櫎锛夈€傛鍓?v1 鍙湁 GET锛屽鑷?AGUI 娑堟伅钀藉簱鏃?`messages.session_id` 澶栭敭澶辫触銆?
### 4. AGUI / Agent 鏀跺彛

- `/api/agui/*`锛氶棶绛?SSE 娴佸紡銆佷細璇濈姸鎬併€佷氦浜掍笂鎶ャ€?- `services/agent_client.py`锛氳褰曠湡瀹?Agent 濂戠害 鈥斺€?绔偣 `POST {AGENT_BASE_URL}/agent/chat`锛圫SE 娴佸紡锛夈€佽韩浠?`X-User-Id` 璇锋眰澶淬€佽姹備綋 `{query, session_id}`銆?- **褰撳墠鍓嶇鐩磋繛 Agent**锛坄VITE_AGUI_BASE_URL` 鎸囧悜 agent锛夛紝鍚庣 `/api/agui/*` 浠呬綔 Agent 鏈帴鍏ユ椂鐨勯檷绾у厹搴曪紙杩斿洖銆屾櫤鑳介棶绛旀湇鍔℃殏鏈帴鍏ワ紝璇风◢鍚庨噸璇曘€傘€嶏級銆?- 涓氬姟钀藉簱锛歚recommendation_logs`锛堜竴琛屼竴涓鎺ㄨ崘浜猴級銆乣feedback`锛堣禐韪╀笁鎬侊級銆?
### 5. 鍙戝竷浜嬩欢淇″彿

- `rag.publish_events` 琛?+ `services/publish_event.py`锛氬唴瀹瑰湪銆屽鏍搁€氳繃鍙戝竷 / 缂栬緫宸插彂甯?/ 鍒犻櫎宸插彂甯冦€嶆椂鍐欎竴鏉?`pending` 浜嬩欢锛屼緵 RAG 鏈嶅姟娑堣垂鍚庤Е鍙?`generate-from-db` + `index` 閲嶆柊绱㈠紩銆傚悗绔彧鍙戜俊鍙凤紝涓嶉噸澶嶅疄鐜板垏鐗?鍚戦噺鍖?鍏ュ簱銆?
---

## 鏁版嵁濂戠害瀵归綈锛圓gent / RAG锛屼互鏈簱涓哄噯锛?
涓夋柟锛堝悗绔?/ agent-service / knowledge-service锛夊師鐢ㄤ袱濂楃煕鐩剧殑鏁版嵁妯″瀷銆傛湰娆￠€氳繃涓€涓?Alembic 杩佺Щ锛坄a7b3c9d1e2f4_agent_compat_views`锛夋妸 agent 鐨勫彧璇绘煡璇㈠榻愬埌鏈簱锛?
| 渚濊禆 | 鏈簱 | agent 鏈熸湜 | 瀵归綈鎵嬫 |
|---|---|---|---|
| 浜哄憳琛?| `users`(P0001, `active` bool) | `people`(p-0001, `status` text, `department` text) | **`public.people` 瑙嗗浘**锛堟槧灏?users锛岃ˉ department/status/role_type 绛夊垪锛?|
| 璐ｄ换琛?| `responsibility_assignments`(person_id+concept_id) | 瀹屾暣璐ｄ换浜嬮」(title/description/owner/time_limit鈥? | **琛ュ垪 + 浠?`agent.concepts`/`users` 鍥炲～** |
| 鐗堟湰鎸囬拡 | 鏃?| `rag_index_pointer`(active_version) | **琛ヨ〃**锛坅ctive_version=0 琛ㄧず銆孯AG 绱㈠紩灏氭湭鏋勫缓銆嶁啋 妫€绱㈣蛋闄嶇骇锛?|

rag 鍏朵綑琛ㄧ粨鏋勫樊寮傦紙`rag_documents`/`rag_chunks`/`rag_index_jobs` 鐨勪袱濂楀垪鍚嶃€乣index_version` INTEGER vs TEXT锛?*涓嶅湪鏈縼绉诲鐞?*锛屼繚鎸佹湰搴?rag 琛ㄤ笉鍔紝鐢?agent 鍥㈤槦鏀瑰叾 rag SQL 閫傞厤锛堣涓嬶級銆?
---

## 寰呭叾浠栧洟闃熻皟鏁?
### Agent 鍥㈤槦锛坅gent-service锛?
1. 杩炲簱閰嶇疆鏀逛负鏈簱锛歚app/config.py` 鈫?`pghost=localhost`銆乣pgdatabase=shouwenzeren`銆乣pguser=swzr_admin`銆乣pgpassword=<数据库口令，见 .env>`銆?2. 璺宠繃 `init_db.py` / `import_v2_data.py`锛堟湰搴撳凡鏈夋暟鎹?+ `people` 瑙嗗浘锛屽嬁閲嶅缓 v2 琛?/ 閲嶆柊鐏屾暟鎹級銆?3. 纭鍏舵煡璇㈠懡涓?`public.people` 瑙嗗浘涓?`responsibility_assignments` 琛ュ垪锛坄_build_user_context` / `directory_search` / `MockResponsibilityRetriever`锛夈€?4. 纭 `/agent/chat` SSE 娴佸紡濂戠害涓庢湰搴?`agent_client.py` 璁板綍涓€鑷达紙`{query, session_id}` + `X-User-Id`锛夈€?
### RAG / Agent 鍥㈤槦锛坘nowledge-service / rag 琛級

1. rag 琛ㄥ啓鍏ラ€傞厤锛歚rag_documents` / `rag_chunks` / `rag_index_jobs` 鍒楀悕涓?`index_version` 绫诲瀷锛圛NTEGER vs TEXT锛変笌鏈簱涓嶅悓锛岄渶鏀瑰叾 rag SQL 閫傞厤锛堣鍥炬晳涓嶄簡鍐欏叆锛夈€?2. 娑堣垂 `rag.publish_events`锛氬悗绔凡鍐?`pending` 浜嬩欢锛屼絾鐩墠娌℃湁娑堣垂鑰咃紝闇€ knowledge-service 鎺ュ叆璋冨害锛岃Е鍙?`generate-from-db` + `index`銆?
### 鍓嶇

1. `stores/sessions.js` 鐨?`loadSessions()` 鏈媶鍚庣鍒嗛〉鍝嶅簲 `{items:[...]}`锛堣鎶婂璞″綋鏁扮粍鍙?`.length`锛夛紝瀵艰嚧鍘嗗彶浼氳瘽姣忔鍒锋柊鍙樉绀轰竴鏉＄┖鐧斤紱`normalizeSession` 璇?camelCase锛坄turnCount`/`updatedAt`锛夎€屽悗绔繑鍥?snake_case锛坄turn_count`/`updated_at`锛夛紝闇€瀵归綈瀛楁鍚嶃€?
---

## 鍓嶅悗绔害瀹?
### 1. 瀛楁鍛藉悕锛歝amelCase

鎵€鏈夊搷搴?JSON 瀛楁鍚嶅潎涓?camelCase锛?
```json
{
  "ownerId": "P0001",
  "ownerName": "鑼呮辰濠?,
  "auditTrail": [...],
  "publishedAt": "2026-08-12",
  "weeklyQueryCount": 12
}
```

璇锋眰浣撳悓鏍锋敮鎸?camelCase锛圥ydantic `alias` 鍏煎锛夈€?
> 渚嬪锛歚GET /sessions` 鐨?`SessionResponse` 鐩墠浠嶈繑鍥?snake_case锛坄turn_count`/`updated_at`锛夛紝鍓嶇浼氳瘽鍒楄〃闇€鎸夋瀵归綈锛堣銆屽緟鍓嶇璋冩暣銆嶏級銆?
### 2. 鍐呭鐘舵€侊細涓枃

| 鏁版嵁搴擄紙鑻辨枃锛?| API 杩斿洖锛堜腑鏂囷級 |
|--------------|--------------|
| `draft` | 鑽夌 |
| `pending_review` | 寰呭鏍?|
| `published` | 宸插彂甯?|
| `rejected` | 宸查┏鍥?|

鍒楄〃绛涢€変粛鐢ㄨ嫳鏂囷細`?status=pending_review`銆?
### 3. 瀹℃牳娴佺▼

- 瀹℃牳鐢ㄤ笓鐢ㄧ鐐?`POST /contents/{id}/audit`锛?*浠呯鐞嗗憳**锛夛紝涓嶇敤 `PUT /contents/{id}`
- 璇锋眰浣擄細`{ action: "approve"|"reject", reason: "" }`
- 瀹℃牳璁板綍鍐欏叆 `auditTrail`锛坖sonb锛夛紝瀛楁锛?  ```json
  {
    "operator": "P0001",
    "operated_at": "2026-08-12T16:30:00+08:00",
    "result": "published",
    "reason": ""
  }
  ```
- 鏃堕棿锛氬寳浜椂闂达紝绮剧‘鍒扮

### 4. 浠栫敾鍍?
- 鎵撴爣绛?`POST /reviews`锛氫紶 `{ personId, tag }`锛屽悗绔嚜鍔ㄨˉ `reviewer` + `date`
- 鍔犺浇"鎴戠殑鏍囩"闇€鍚堝苟锛歚/reviews/sent`锛堝彂鍑虹殑锛? `/people/{myId}/reviews`锛堟敹鍒扮殑锛?
### 5. 鍐呭 ID

- 绉嶅瓙鏁版嵁锛歚A00001` ~ `A00607`
- 鎵嬪姩鍒涘缓锛歚C00001`銆乣C00002`...锛? 浣嶅簭鍙凤級

---

## 鍓嶇淇敼娓呭崟

鍓嶇鍚屽鍩轰簬鏃т唬鐮侀渶鍚屾浠ヤ笅鏂囦欢锛坄github-sync/src/` 涓嬶級锛?
| 鏂囦欢 | 鏀瑰姩 |
|------|------|
| `components/admin/AuditList.vue` | 瀹℃牳鍗＄墖鍙偣鍑?+ 灞曠ず姝ｆ枃 + `@click.stop` |
| `views/MineView.vue` | `v-if="!profile"` 闃插姞杞藉穿婧?|
| `views/ContentDetailView.vue` | 瀹℃牳瀛楁 `operator` / `operated_at` |
| `stores/content.js` | 瀹℃牳鏀圭敤 `POST /{id}/audit` |
| `stores/reviews.js` | 鍚屾椂鍔犺浇鍙戝嚭+鏀跺埌鏍囩 |
| `services/api/content.js` | 鏂板 `auditContent` 鏂规硶 |
| `stores/sessions.js` | 浼氳瘽鍔犺浇鎷嗗垎椤?+ 瀛楁鍚嶅榻愶紙瑙併€屽緟鍓嶇璋冩暣銆嶏級 |

---

## Swagger 浣跨敤璇存槑

1. 鍚姩鍚庣 鈫?`http://localhost:8000/docs`
2. 鍏堣皟 `POST /auth/login`锛岀敤 `p0001` / `<种子账号口令，见 .env>` 鐧诲綍
3. 澶嶅埗 `token`
4. 鐐瑰彸涓婅 **Authorize** 鈫?杈撳叆 `Bearer <token>`
5. 鎵€鏈夐渶閴存潈鎺ュ彛鍙洿鎺ュ湪 Swagger 涓婃祴璇?
---

## 鏁版嵁搴?
| 椤圭洰 | 璇存槑 |
|------|------|
| 鏁版嵁搴?| PostgreSQL 17 + pgvector锛坄swzr-pg`锛岃 `docker-compose.yml`锛?|
| 杩佺Щ | `alembic upgrade head` |
| 鐢ㄦ埛 | `swzr_admin` / `<数据库口令，见 .env>` |
| Schema | `public`锛堜笟鍔★級/ `agent`锛堟蹇电瓑锛? `rag`锛堢储寮?+ `publish_events` + `rag_index_pointer`锛?|
| 浜哄憳 | 300 浜猴紙P0001~P0300锛?|
| 鍐呭 | 607 鏉＄瀛?+ 鎵嬪姩鍒涘缓 |
| 閮ㄩ棬 | 30 涓紙1 鈫?4 鈫?10 鈫?15锛?|
