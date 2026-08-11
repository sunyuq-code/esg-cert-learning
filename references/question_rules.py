#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Question Generation Rules Engine (题库生成规则引擎)
根据 v3.0 量化规则计算每个知识点应生成的题目数量与题型分配。

规则要点:
- 复杂度总分 = CL(内容长度) + CT(内容类型) + ET(考察类型) + D(难度), 范围 4~14
- 4-5分  -> +0  (S1 M1 T1 A1, 共4题)
- 6-7分  -> +2  (S2 M2 T1 A1, 共6题)
- 8-9分  -> +3  (S3 M2 T1 A1, 共7题)
- 10-11分-> +5  (S3 M3 T1 A2, 共9题)
- 12-14分-> +8  (S3 M4 T2 A3, 共12题)
"""

# 内容类型 -> (分值, 考察类型-基础难度, 考察类型-中高级难度)
CONTENT_TYPES = {
    "Definition":      (1, "Memorization", "Understanding"),
    "History":         (1, "Memorization", "Understanding"),
    "List":            (2, "Memorization", "Understanding"),
    "Classification":  (2, "Understanding", "Understanding"),
    "Policy":          (2, "Memorization", "Understanding"),
    "Comparison":      (3, "Analysis",     "Analysis"),
    "Concept":         (3, "Understanding", "Analysis"),
    "Framework":       (4, "Understanding", "Understanding"),
    "Process":         (4, None,           "Application"),
    "Analysis":        (3, None,           "Analysis"),
}

EXAM_TYPE_SCORES = {
    "Memorization": 1,
    "Understanding": 2,
    "Application": 3,
    "Analysis": 3,
}

DIFFICULTY_SCORES = {"basic": 1, "intermediate": 2, "advanced": 3}

# 内容长度分级 (按 explanation 字符数)
def content_length_score(explanation):
    """按内容长度计算 CL 分值 (1-4)。"""
    n = len(explanation or "")
    if n < 80:
        return 1
    elif n < 120:
        return 2
    elif n < 180:
        return 3
    else:
        return 4

# 分数 -> 目标题型分配
TARGET_MAP = [
    ((4, 5),  {"S": 1, "M": 1, "T": 1, "A": 1}),   # +0, 共4
    ((6, 7),  {"S": 2, "M": 2, "T": 1, "A": 1}),   # +2, 共6
    ((8, 9),  {"S": 3, "M": 2, "T": 1, "A": 1}),   # +3, 共7
    ((10, 11), {"S": 3, "M": 3, "T": 1, "A": 2}),  # +5, 共9
    ((12, 14), {"S": 3, "M": 4, "T": 2, "A": 3}),  # +8, 共12
]

TYPE_ORDER = ["S", "M", "T", "A"]
TYPE_NAMES = {
    "S": "single_choice", "M": "multiple_choice",
    "T": "true_false", "A": "short_answer",
}


def classify_content_type(kp):
    """根据知识点内容关键词自动分类内容类型。返回 (类型代码, 类型名)。"""
    text = f"{kp.get('topic', '')} {kp.get('concept', '')} {kp.get('explanation', '')}"
    rules = [
        ("Definition", ["定义", "是指", "缩写", "含义", "概念是"]),
        ("History", ["历程", "起源", "里程碑", "发展史", "演变", "历史"]),
        ("Comparison", ["区别", "差异", "对比", "vs", "比较", "关系"]),
        ("Classification", ["两大类", "分类", "分为", "类别"]),
        ("Policy", ["政策", "监管", "法规", "指令", "要求", "指引", "准则体系"]),
        ("Process", ["流程", "步骤", "编制", "方法论", "程序", "阶段"]),
        ("Framework", ["框架", "支柱", "结构", "体系", "标准", "模型"]),
        ("List", ["包括", "形式", "类别", "要素", "方面", "组成"]),
        ("Analysis", ["影响", "风险", "问题", "争议", "挑战", "分析"]),
        ("Concept", ["理念", "本质", "特征", "作用", "意义", "原则"]),
    ]
    for ctype, keywords in rules:
        for kw in keywords:
            if kw in text:
                return ctype
    return "Concept"


def get_et_score(ct_type, difficulty):
    """根据内容类型+难度确定考察类型分值 ET (1-3)。"""
    ct = CONTENT_TYPES.get(ct_type, CONTENT_TYPES["Concept"])
    _, base_et, adv_et = ct
    d_score = DIFFICULTY_SCORES.get(difficulty, 1)
    et_name = adv_et if d_score >= 2 and adv_et else (base_et or "Understanding")
    return EXAM_TYPE_SCORES.get(et_name, 2)


def compute_score(kp, ct_type=None):
    """计算知识点复杂度总分 (4-14)。返回 dict。"""
    explanation = kp.get("explanation", "")
    cl = content_length_score(explanation)

    if ct_type is None:
        ct_type = classify_content_type(kp)
    ct_score = CONTENT_TYPES.get(ct_type, (3,))[0]

    difficulty = kp.get("level", "basic")
    d_score = DIFFICULTY_SCORES.get(difficulty, 1)
    et_score = get_et_score(ct_type, difficulty)

    total = cl + ct_score + et_score + d_score
    return {
        "cl": cl, "ct": ct_type, "ct_score": ct_score,
        "et_score": et_score, "d_score": d_score,
        "difficulty": difficulty, "total": total,
    }


def target_for_score(total):
    """根据总分返回目标题型分配 dict {S,M,T,A}。"""
    for (lo, hi), target in TARGET_MAP:
        if lo <= total <= hi:
            return dict(target)
    return dict(TARGET_MAP[0][1])


def kp_target(kp, ct_type=None):
    """计算单个知识点的目标题型分配。"""
    info = compute_score(kp, ct_type)
    return info, target_for_score(info["total"])


def missing_questions(current_by_type, target):
    """计算需要新增的题型数量。current_by_type: {'S':n,...}"""
    need = {}
    for t in TYPE_ORDER:
        need[t] = max(0, target[t] - current_by_type.get(t, 0))
    return need


def type_code_to_name(code):
    return TYPE_NAMES[code]


def name_to_type_code(qtype):
    for code, name in TYPE_NAMES.items():
        if name == qtype:
            return code
    return None


# ===========================================================================
# 权威评分表 (来自 question_generation_rules.md v3.0 的74-KP手工分类结果)
# 用于题库生成与规则合规测试，保证与规则文档完全一致。
# 格式: kp_id -> (ct_type, total_score)
# ===========================================================================
AUTHORITATIVE_SCORES = {
    "ESG-T-001": ("Definition", 5), "ESG-T-002": ("History", 7),
    "ESG-T-003": ("Comparison", 8), "ESG-T-004": ("Definition", 4),
    "ESG-T-005": ("List", 6), "ESG-T-006": ("Policy", 7),
    "ESG-T-007": ("Concept", 7), "ESG-T-008": ("Concept", 7),
    "ESG-T-009": ("Policy", 6), "ESG-T-010": ("Analysis", 9),
    "ESG-T-011": ("History", 7), "ESG-T-012": ("History", 8),
    "ESG-T-013": ("Policy", 7),
    "ESG-S-001": ("Framework", 10), "ESG-S-002": ("Framework", 10),
    "ESG-S-003": ("Framework", 11), "ESG-S-004": ("Framework", 11),
    "ESG-S-005": ("Framework", 13), "ESG-S-006": ("Framework", 9),
    "ESG-S-007": ("Framework", 11), "ESG-S-008": ("List", 6),
    "ESG-S-009": ("Concept", 10), "ESG-S-010": ("Concept", 9),
    "ESG-S-011": ("Comparison", 11), "ESG-S-012": ("Process", 11),
    "ESG-S-013": ("Policy", 8), "ESG-S-014": ("Policy", 8),
    "ESG-S-015": ("Policy", 7),
    "ESG-I-001": ("Definition", 5), "ESG-I-002": ("List", 6),
    "ESG-I-003": ("History", 7), "ESG-I-004": ("Definition", 6),
    "ESG-I-005": ("Definition", 6), "ESG-I-006": ("Definition", 7),
    "ESG-I-007": ("Concept", 9), "ESG-I-008": ("Definition", 6),
    "ESG-I-009": ("Concept", 10), "ESG-I-010": ("Definition", 5),
    "ESG-I-011": ("Definition", 5), "ESG-I-012": ("List", 8),
    "ESG-I-013": ("Concept", 9),
    "ESG-R-001": ("Definition", 5), "ESG-R-002": ("List", 6),
    "ESG-R-003": ("Process", 11), "ESG-R-004": ("Framework", 10),
    "ESG-R-005": ("Framework", 10), "ESG-R-006": ("Framework", 9),
    "ESG-R-007": ("Analysis", 10), "ESG-R-008": ("Analysis", 11),
    "ESG-R-009": ("List", 10),
    "ESG-H-001": ("Definition", 6), "ESG-H-002": ("List", 8),
    "ESG-H-003": ("List", 8), "ESG-H-004": ("List", 9),
    "ESG-H-005": ("Analysis", 11), "ESG-H-006": ("Framework", 9),
    "ESG-H-007": ("List", 6), "ESG-H-008": ("Framework", 10),
    "ESG-H-009": ("List", 9), "ESG-H-010": ("Concept", 11),
    "ESG-H-011": ("Process", 11), "ESG-H-012": ("Process", 11),
    "ESG-H-013": ("Framework", 13), "ESG-H-014": ("Process", 11),
    "ESG-H-015": ("List", 8), "ESG-H-016": ("Process", 13),
    "ESG-H-017": ("Classification", 8), "ESG-H-018": ("Process", 13),
    "ESG-H-019": ("Framework", 12), "ESG-H-020": ("Concept", 9),
    "ESG-H-021": ("List", 8), "ESG-H-022": ("Concept", 9),
    "ESG-H-023": ("Concept", 9), "ESG-H-024": ("Analysis", 11),
}


def kp_target_authoritative(kp):
    """使用权威评分表计算目标，未收录时回退到自动计算。"""
    kp_id = kp.get("id", "")
    if kp_id in AUTHORITATIVE_SCORES:
        ct_type, total = AUTHORITATIVE_SCORES[kp_id]
        target = target_for_score(total)
        info = compute_score(kp, ct_type)
        info["total"] = total
        return info, target
    return kp_target(kp)
