"""Agent 自测用例库(feature/real-data 分支版,适配真实数据库 208人/32部门/310文)。

与 run_agent_tests.py 配套;每条用例一个会话,逐轮断言。
数据基线:shouwenzeren_newdb(2026-08-20 数据库团队 dump + schema 迁移)。

覆盖:
- 找人:正式责任/标签领域/技能/文章作者/联系方式
- 写操作:资料维护四类/他人画像/内容发布
- 多轮:续接合并/记忆追问/防误续接
- 边界:问候/无关/诚实空答
"""

CASES = [
    # ============ 找人:正式责任 ============
    {"name": "正式责任-综合管理", "category": "找人/正式责任",
     "session": [{"q": "谁负责综合管理",
                  "expect": {"intent": "find_person", "contains": ["杨晓彦"]}}]},
    {"name": "正式责任-数仓开发", "category": "找人/正式责任",
     "session": [{"q": "数仓开发找谁",
                  "expect": {"intent": "find_person", "contains": ["兰昕蕾", "丁晨"]}}]},
    {"name": "正式责任+领域-监管报送", "category": "找人/正式责任",
     "session": [{"q": "监管报送找谁",
                  "expect": {"contains": ["邹小芳"]}}]},

    # ============ 找人:标签/技能/文章 ============
    {"name": "技能找人-风险模型", "category": "找人/技能",
     "session": [{"q": "谁懂风险模型",
                  "expect": {"contains": ["蒋捷", "许天凝", "李梦霄", "杨沁怡", "于俊杰"]}}]},
    {"name": "文章作者-智能问数", "category": "找人/文章",
     "session": [{"q": "《智能问数的工作方法与要点》是谁写的",
                  "expect": {"contains": ["刘成彦"]}}]},
    {"name": "联系方式-刘成彦", "category": "找人/联系方式",
     "session": [{"q": "刘成彦的电话是多少",
                  "expect": {"contains": ["18800000001"]}}]},

    # ============ 写操作:资料维护 ============
    {"name": "改联系方式", "category": "写/资料",
     "session": [{"q": "修改我的联系方式为13900000000",
                  "expect": {"card_type": "profile", "card_contains": ["13900000000"]}}]},
    {"name": "改自画像-覆盖", "category": "写/资料",
     "session": [{"q": "修改我的自画像为热爱技术的工程师",
                  "expect": {"card_type": "profile", "card_contains": ["热爱技术的工程师"]}}]},
    {"name": "自我标签", "category": "写/资料",
     "session": [{"q": "给我自己添加标签：数据治理",
                  "expect": {"card_type": "profile", "card_contains": ["数据治理"]}}]},
    {"name": "负责领域变更", "category": "写/资料",
     "session": [{"q": "我现在负责图数据库",
                  "expect": {"card_type": "profile", "card_contains": ["图数据库"]}}]},

    # ============ 写操作:他人画像/发布 ============
    {"name": "他人画像", "category": "写/画像",
     "session": [{"q": "给冉紫萱增加标签：产品思维",
                  "expect": {"card_type": "review", "card_contains": ["冉紫萱", "产品思维"]}}]},
    {"name": "名录无人-张总", "category": "写/刁钻",
     "session": [{"q": "给张总打个标签：负责",
                  "expect": {"not_contains": ["confirmation"], "answer_has": ["没有找到", "名录", "确认"]}}]},
    {"name": "发布带正文", "category": "写/发布",
     "session": [{"q": "我想发布一篇内容标题是数据治理经验，正文：数据治理要先定标准，再落平台，最后抓运营闭环。",
                  "expect": {"card_type": "content",
                             "card_contains": ["数据治理经验", "定标准", "运营闭环"]}}]},

    # ============ 多轮:续接与记忆 ============
    {"name": "三连追加自画像", "category": "多轮/续接",
     "session": [
         {"q": "把我的自画像改为喜欢打篮球", "expect": {"card_type": "profile", "card_contains": ["喜欢打篮球"]}},
         {"q": "再加一句 也喜欢游泳", "expect": {"card_type": "profile", "continuation": True,
                                              "card_contains": ["喜欢打篮球", "也喜欢游泳"]}},
         {"q": "再加一句 还有羽毛球", "expect": {"card_type": "profile", "continuation": True,
                                              "card_contains": ["羽毛球"]}},
     ]},
    {"name": "联系方式替换追问", "category": "多轮/续接",
     "session": [
         {"q": "修改我的联系方式为13800000000", "expect": {"card_type": "profile", "card_contains": ["13800000000"]}},
         {"q": "换成13900000001", "expect": {"card_type": "profile", "continuation": True,
                                          "card_contains": ["13900000001"]}},
     ]},
    {"name": "追问补全人名", "category": "多轮/记忆",
     "session": [
         {"q": "冉紫萱是谁", "expect": {"contains": ["冉紫萱"]}},
         {"q": "她的电话呢", "expect": {"contains": ["18800000002"]}},
     ]},
    {"name": "防误续接-新话题", "category": "多轮/防误伤",
     "session": [
         {"q": "把我的自画像改为喜欢打球", "expect": {"card_type": "profile"}},
         {"q": "谁负责综合管理", "expect": {"intent": "find_person", "contains": ["杨晓彦"],
                                           "continuation": False}},
     ]},

    # ============ 边界 ============
    {"name": "问候", "category": "边界",
     "session": [{"q": "你好", "expect": {"no_card": True}}]},
    {"name": "无关问题", "category": "边界",
     "session": [{"q": "今天天气怎么样", "expect": {"no_card": True}}]},
    {"name": "不存在领域", "category": "边界/诚实空答",
     "session": [{"q": "谁负责量子计算机维修", "expect": {"honest_empty": True}}]},
]
