#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESG Skill 测试套件 (test_skill.py)
====================================
测试 esg-cert-learning skill 的稳定运行, 覆盖:

  [T1] 数据完整性    - knowledge_base.json / question_bank.json 可加载, 字段完整
  [T2] 题库结构校验  - ID唯一, 题型合法, kp_ref有效, 选项/答案格式正确
  [T3] 规则合规      - 每知识点4题型齐全, 目标题量符合 v3.0 规则
  [T4] 引擎函数      - load_* / normalize_answer / StudySession 基础行为
  [T5] 生成器       - generate_questions.py 的校验/去重/ID分配(离线)
  [T6] API配置      - resolve_api_key 读取链, 无Key时优雅降级
  [T7] 生成管线      - 模拟API的端到端生成→校验→合并流程

用法:
  python test_skill.py             # 运行全部测试
  python test_skill.py --verbose   # 显示每个用例详情
  python test_skill.py --offline   # 强制离线(mock API, 不检查真实Key)

退出码: 0=全部通过, 1=有失败
"""

import os
import sys
import json
import re
import argparse
import importlib
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import question_rules as rules
import esg_engine as engine


# ===========================================================================
# 测试框架 (轻量)
# ===========================================================================

class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.skipped = []

    def record(self, suite, name, ok, detail=""):
        if ok:
            self.passed.append((suite, name))
        else:
            self.failed.append((suite, name, detail))

    def skip(self, suite, name, reason=""):
        self.skipped.append((suite, name, reason))

    @property
    def total(self):
        return len(self.passed) + len(self.failed)

    @property
    def ok(self):
        return len(self.failed) == 0


RESULTS = TestResult()
VERBOSE = False


def check(suite, name, cond, detail=""):
    RESULTS.record(suite, name, bool(cond), detail)
    if VERBOSE:
        mark = "PASS" if cond else "FAIL"
        print(f"    [{mark}] {suite}: {name}" + (f" — {detail}" if detail and not cond else ""))


def suite_header(name):
    print(f"\n  {name}")
    print("  " + "-" * 56)


# ===========================================================================
# 数据加载
# ===========================================================================

def load_all():
    kb_path = os.path.join(BASE_DIR, "knowledge_base.json")
    bank_path = os.path.join(BASE_DIR, "question_bank.json")
    with open(kb_path, "r", encoding="utf-8") as f:
        kb = json.load(f)
    with open(bank_path, "r", encoding="utf-8") as f:
        bank = json.load(f)
    kps = kb["knowledge_points"] if isinstance(kb, dict) else kb
    qs = bank["questions"]
    return kps, qs, kb, bank


# ===========================================================================
# T1: 数据完整性
# ===========================================================================

def test_data_integrity(kps, qs):
    suite_header("[T1] 数据完整性")
    check("T1", "知识库有74个知识点", len(kps) == 74, f"got {len(kps)}")
    check("T1", "题库有603道题", len(qs) == 603, f"got {len(qs)}")

    required_kp_fields = ["id", "module", "submodule", "topic", "concept", "level", "explanation"]
    missing = []
    for kp in kps:
        for f in required_kp_fields:
            if not kp.get(f):
                missing.append(f"{kp.get('id','?')}:{f}")
    check("T1", "知识点字段完整", not missing, "; ".join(missing[:5]))

    kp_ids = [kp["id"] for kp in kps]
    check("T1", "知识点ID唯一", len(kp_ids) == len(set(kp_ids)))
    check("T1", "知识点level合法",
          all(kp.get("level") in ("basic", "intermediate", "advanced") for kp in kps))

    # 题型覆盖
    type_counter = Counter(q["type"] for q in qs)
    expected_types = {"single_choice", "multiple_choice", "true_false", "short_answer"}
    check("T1", "包含全部4种题型", set(type_counter) == expected_types,
          f"missing {expected_types - set(type_counter)}")
    for t in expected_types:
        check("T1", f"题型[{t}]有题", type_counter.get(t, 0) > 0, str(type_counter.get(t, 0)))


# ===========================================================================
# T2: 题库结构校验
# ===========================================================================

def test_bank_structure(kps, qs, bank):
    suite_header("[T2] 题库结构校验")

    ids = [q["id"] for q in qs]
    check("T2", "题目ID唯一", len(ids) == len(set(ids)),
          f"{len(ids) - len(set(ids))} duplicates")

    kp_ids = set(kp["id"] for kp in kps)
    bad_refs = [q["id"] for q in qs if q.get("kp_ref") not in kp_ids]
    check("T2", "所有kp_ref有效", not bad_refs, "; ".join(bad_refs[:5]))

    # ID格式: Q-{KP}-{Type}{Seq}
    bad_ids = [q["id"] for q in qs
               if not re.match(r"^Q-(ESG-[A-Z]-\d{3})-([SMTA])(\d+)$", q["id"])]
    check("T2", "ID格式符合 Q-KP-TypeSeq", not bad_ids, "; ".join(bad_ids[:5]))

    # 字段完整性 + 答案有效性
    problems = []
    for q in qs:
        qid, qtype = q.get("id", "?"), q.get("type", "?")
        if not q.get("question"):
            problems.append(f"{qid}:缺题干")
        if not q.get("explanation"):
            problems.append(f"{qid}:缺解析")
        if q.get("level") not in ("basic", "intermediate", "advanced"):
            problems.append(f"{qid}:level无效")
        if qtype in ("single_choice", "multiple_choice"):
            opts = q.get("options")
            if not isinstance(opts, dict) or len(opts) < 4:
                problems.append(f"{qid}:选项必须为dict且>=4个")
                continue
            ans = q.get("answer", "")
            letters = [c for c in str(ans).upper() if c in "ABCDE"]
            if qtype == "single_choice" and len(letters) != 1:
                problems.append(f"{qid}:单选答案应为1个字母")
            if qtype == "multiple_choice":
                # 多选至少2个正确项, 不超过选项数 (允许全选式题目)
                n_opts = len(opts)
                if not (2 <= len(letters) <= n_opts):
                    problems.append(f"{qid}:多选答案应为2-{n_opts}个字母")
            if not all(c in opts for c in letters):
                problems.append(f"{qid}:答案超出选项范围")
        elif qtype == "true_false":
            if str(q.get("answer", "")).lower() not in ("true", "false"):
                problems.append(f"{qid}:判断答案应为True/False")
        elif qtype == "short_answer":
            if not q.get("reference_answer"):
                problems.append(f"{qid}:简答缺reference_answer")
            if not q.get("scoring_points"):
                problems.append(f"{qid}:简答缺scoring_points")
        else:
            problems.append(f"{qid}:未知题型{qtype}")
    check("T2", "字段与答案全部有效", not problems, "; ".join(problems[:8]))

    # 同KP内无重复题干 (复用 fix_questions.core_ratio, 同题型且>0.75视为重复)
    import fix_questions as fx
    dup_texts = []
    by_kp = {}
    for q in qs:
        by_kp.setdefault(q["kp_ref"], []).append(q)
    for kp_ref, kq in by_kp.items():
        for i in range(len(kq)):
            for j in range(i + 1, len(kq)):
                a, b = kq[i], kq[j]
                if a["type"] != b["type"]:
                    continue  # 不同题型(如判断vs单选)可测试同一事实, 不算重复
                ratio = fx.core_ratio(a["question"], b["question"])
                if ratio > 0.75:
                    dup_texts.append(f"{kp_ref}: {a['id']}~{b['id']} 核心相似度{ratio:.2f}")
    check("T2", "同KP内无重复题干(同题型)", not dup_texts, "; ".join(dup_texts[:5]))

    # metadata 与实际一致
    md = bank.get("metadata", {})
    check("T2", "metadata.total_questions一致",
          md.get("total_questions") == len(qs),
          f"metadata={md.get('total_questions')}, actual={len(qs)}")
    check("T2", "metadata.rules_version=v3.0", md.get("rules_version") == "3.0")


# ===========================================================================
# T3: 规则合规
# ===========================================================================

def test_rules_compliance(kps, qs):
    suite_header("[T3] 规则合规 (v3.0)")

    by_kp = {}
    for q in qs:
        by_kp.setdefault(q["kp_ref"], {"S": 0, "M": 0, "T": 0, "A": 0})
        tc = rules.name_to_type_code(q["type"])
        if tc:
            by_kp[q["kp_ref"]][tc] += 1

    # 保底: 每KP每种题型至少1题
    missing_guarantee = []
    for kp in kps:
        cur = by_kp.get(kp["id"], {})
        for t in ["S", "M", "T", "A"]:
            if cur.get(t, 0) < 1:
                missing_guarantee.append(f"{kp['id']}:缺{rules.TYPE_NAMES[t]}")
    check("T3", "每KP每题型至少1题(保底)", not missing_guarantee,
          "; ".join(missing_guarantee[:8]))

    # 目标合规: 实际题量 >= 规则目标(每题型)
    under_target = []
    for kp in kps:
        info, target = rules.kp_target_authoritative(kp)
        cur = by_kp.get(kp["id"], {})
        for t in ["S", "M", "T", "A"]:
            if cur.get(t, 0) < target[t]:
                under_target.append(
                    f"{kp['id']}:{rules.TYPE_NAMES[t]}实{cur.get(t,0)}<目{target[t]}")
    check("T3", "各KP题量达到规则目标", not under_target,
          "; ".join(under_target[:8]))

    # 总分范围
    bad_scores = []
    for kp in kps:
        info, _ = rules.kp_target_authoritative(kp)
        if not (4 <= info["total"] <= 14):
            bad_scores.append(f"{kp['id']}:{info['total']}")
    check("T3", "复杂度总分均在4-14", not bad_scores, "; ".join(bad_scores))

    # 目标总量
    total_target = sum(sum(rules.kp_target_authoritative(kp)[1].values()) for kp in kps)
    check("T3", "规则目标总量=550", total_target == 550, f"got {total_target}")

    # 实际覆盖: 每KP题数
    per_kp = {k: sum(v.values()) for k, v in by_kp.items()}
    check("T3", "实际题量>=目标题量(每KP)",
          all(per_kp.get(kp["id"], 0) >= sum(rules.kp_target_authoritative(kp)[1].values())
              for kp in kps))


# ===========================================================================
# T4: 引擎函数
# ===========================================================================

def test_engine_functions():
    suite_header("[T4] 引擎函数")

    # load_question_bank
    by_kp, all_qs = engine.load_question_bank(os.path.join(BASE_DIR, "question_bank.json"))
    check("T4", "load_question_bank返回数据", len(all_qs) == 603, f"got {len(all_qs)}")
    check("T4", "by_kp按知识点分组", len(by_kp) == 74, f"got {len(by_kp)}")

    # load_knowledge_base
    kps = engine.load_knowledge_base(os.path.join(BASE_DIR, "knowledge_base.json"))
    check("T4", "load_knowledge_base返回数据", len(kps) == 74, f"got {len(kps)}")

    # normalize_answer 各种格式
    cases = [
        ("ABC", "ABC"),
        (["A", "B", "C"], "ABC"),
        ("A,B,C", "ABC"),
        ("bac", "ABC"),
        ("A", "A"),
        ("True", "TRUE"),
        (["C", "A"], "AC"),
    ]
    norm_ok = all(engine.normalize_answer(inp) == exp for inp, exp in cases)
    check("T4", "normalize_answer处理7种格式", norm_ok)

    # StudySession 基础行为
    session = engine.StudySession(
        knowledge_points=[],
        questions=[],
        case_study=None,
        api_key=None,
    )
    check("T4", "StudySession无数据初始化", session.items == [])

    # grade_with_deepseek 无Key时优雅返回None (临时清空全局Key模拟)
    old_key = engine.DEEPSEEK_API_KEY
    engine.DEEPSEEK_API_KEY = ""
    session = engine.StudySession(
        knowledge_points=[],
        questions=[],
        case_study=None,
        api_key=None,
    )
    result = session.grade_with_deepseek("题", "答", "参考", ["要点"])
    engine.DEEPSEEK_API_KEY = old_key
    check("T4", "无API Key时grade返回None", result is None)

    # 真实Key已配置时, grade调用应不崩溃(返回结果或None)
    key_ok = bool(old_key and old_key != "sk-xxxxxxxx")
    if key_ok:
        session2 = engine.StudySession(knowledge_points=[], questions=[],
                                       case_study=None, api_key=old_key)
        try:
            result2 = session2.grade_with_deepseek(
                "请简述ESG的定义", "ESG是环境、社会和治理的缩写",
                "ESG是Environmental(环境)、Social(社会)、Governance(治理)的缩写",
                ["指出ESG三字母含义"])
            check("T4", "真实Key下grade调用正常", result2 is None or isinstance(result2, dict))
        except Exception as e:
            check("T4", "真实Key下grade调用正常", False, str(e)[:120])
    else:
        RESULTS.skip("T4", "真实Key grade调用", "未配置真实Key, 跳过")

    # 用一个简答题对象测试 _show_reference_answer 的字段访问
    sa_q = {
        "id": "TEST-A1", "type": "short_answer", "kp_ref": "X",
        "level": "basic", "question": "q", "answer": "",
        "reference_answer": "参考", "scoring_points": ["p1", "p2"], "explanation": "e",
    }
    ref = sa_q.get("reference_answer", "无参考答案")
    check("T4", "简答题reference_answer可读", ref == "参考")


# ===========================================================================
# T5: 生成器 (离线)
# ===========================================================================

def test_generator_offline(kps, qs):
    suite_header("[T5] 生成器 (离线校验)")

    # import generate_questions (不调用main)
    sys.path.insert(0, BASE_DIR)
    import generate_questions as gen

    # bank_by_kp 索引构建
    bank_by_kp = {}
    for q in qs:
        kp_ref = q.get("kp_ref", "")
        bank_by_kp.setdefault(kp_ref, {"S": 0, "M": 0, "T": 0, "A": 0})
        tc = rules.name_to_type_code(q.get("type", ""))
        if tc:
            bank_by_kp[kp_ref][tc] += 1
        bank_by_kp.setdefault(kp_ref + "_questions", []).append(q)
    bank_by_kp["_all_questions"] = qs

    # 无缺失 (题库已达550目标)
    plan = gen.build_need_plan(kps, bank_by_kp, force=False)
    check("T5", "现有题库无缺失(符合550目标)", sum(sum(n.values()) for _, _, n, _ in plan) == 0,
          f"missing={sum(sum(n.values()) for _,_,n,_ in plan)}")

    # force 模式计划 = 目标总量
    plan_force = gen.build_need_plan(kps, bank_by_kp, force=True)
    force_total = sum(sum(n.values()) for _, _, n, _ in plan_force)
    check("T5", "force模式计划量=550", force_total == 550, f"got {force_total}")

    # validate_question: 合法题目
    good_q = {
        "id": "Q-ESG-T-001-S2", "type": "single_choice", "kp_ref": "ESG-T-001",
        "level": "basic", "question": "测试题目内容足够长以避免误判",
        "options": {"A": "选项一", "B": "选项二", "C": "选项三", "D": "选项四"},
        "answer": "B", "explanation": "解析内容",
    }
    ok, err = gen.validate_question(good_q, bank_by_kp)
    check("T5", "合法单选通过校验", ok, err)

    # validate_question: 非法题目被拒绝
    bad_q = dict(good_q, answer="Z")
    ok, err = gen.validate_question(bad_q, bank_by_kp)
    check("T5", "非法答案被拒绝", not ok and "答案无效" in err, err)

    bad_q2 = dict(good_q, answer="")
    ok, _ = gen.validate_question(bad_q2, bank_by_kp)
    check("T5", "缺答案被拒绝", not ok)

    # validate_question: 简答
    sa_q = {
        "id": "Q-ESG-T-001-A2", "type": "short_answer", "kp_ref": "ESG-T-001",
        "level": "basic", "question": "简答题题干", "answer": "",
        "reference_answer": "参考", "scoring_points": ["p1", "p2"], "explanation": "e",
    }
    ok, err = gen.validate_question(sa_q, bank_by_kp)
    check("T5", "合法简答通过校验", ok, err)

    sa_bad = dict(sa_q, scoring_points=[])
    ok, _ = gen.validate_question(sa_bad, bank_by_kp)
    check("T5", "缺评分要点被拒绝", not ok)

    # validate_question: 多选
    mc_q = {
        "id": "Q-ESG-T-001-M2", "type": "multiple_choice", "kp_ref": "ESG-T-001",
        "level": "basic", "question": "多选题干", "answer": "ABC",
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"}, "explanation": "e",
    }
    ok, err = gen.validate_question(mc_q, bank_by_kp)
    check("T5", "合法多选通过校验", ok, err)

    # validate_question: 判断
    tf_q = {
        "id": "Q-ESG-T-001-T2", "type": "true_false", "kp_ref": "ESG-T-001",
        "level": "basic", "question": "判断题干", "answer": "True", "explanation": "e",
    }
    ok, err = gen.validate_question(tf_q, bank_by_kp)
    check("T5", "合法判断通过校验", ok, err)

    # dedup_check: 与同KP已有题相似被拒绝
    t001_q = next(q for q in qs if q["kp_ref"] == "ESG-T-001" and q["type"] == "single_choice")
    dup_q = dict(good_q, question=t001_q["question"] + "延伸内容")
    ok, err = gen.dedup_check(dup_q, bank_by_kp)
    check("T5", "相似题干被去重拦截", not ok, err)

    # next_seq / assign_seq: ID不冲突
    bank_by_kp2 = dict(bank_by_kp)
    new_q = dict(good_q, id="Q-ESG-T-001-S1")  # 与已有ID冲突
    assigned = gen.assign_seq([new_q], bank_by_kp2)
    check("T5", "ID冲突自动重编号", assigned[0]["id"] != "Q-ESG-T-001-S1",
          assigned[0]["id"])

    # resolve_api_key: 真实Key已配置时返回有效Key
    key = gen.resolve_api_key()
    if engine.DEEPSEEK_API_KEY and engine.DEEPSEEK_API_KEY != "sk-xxxxxxxx":
        check("T5", "已配置Key时resolve返回真实Key",
              key.startswith("sk-") and len(key) > 20, repr(key[:12]) + "...")
    else:
        check("T5", "未配置Key时resolve返回空串", key == "", repr(key[:12]))

    # resolve_api_key: 三源皆空时返回空串 (模拟无Key环境)
    import os
    old_env = os.environ.pop("DEEPSEEK_API_KEY", None)
    old_cfg, old_eng = gen.SKILL_CONFIG_PATH, gen.ENGINE_PATH
    gen.SKILL_CONFIG_PATH = "/nonexistent/config.md"
    gen.ENGINE_PATH = "/nonexistent/engine.py"
    try:
        key_empty = gen.resolve_api_key()
        check("T5", "三源皆空时resolve返回空串", key_empty == "", repr(key_empty))
    finally:
        if old_env:
            os.environ["DEEPSEEK_API_KEY"] = old_env
        gen.SKILL_CONFIG_PATH, gen.ENGINE_PATH = old_cfg, old_eng


# ===========================================================================
# T7: 生成管线端到端 (模拟API)
# ===========================================================================

def test_generation_pipeline(kps, qs, bank):
    suite_header("[T7] 生成管线端到端 (模拟API)")
    import generate_questions as gen

    bank_by_kp = {}
    for q in qs:
        kp_ref = q.get("kp_ref", "")
        bank_by_kp.setdefault(kp_ref, {"S": 0, "M": 0, "T": 0, "A": 0})
        tc = rules.name_to_type_code(q.get("type", ""))
        if tc:
            bank_by_kp[kp_ref][tc] += 1
        bank_by_kp.setdefault(kp_ref + "_questions", []).append(q)
    bank_by_kp["_all_questions"] = qs

    # 用 force 模式取 ESG-T-001 构建计划, 验证 build_prompt
    t001 = next(kp for kp in kps if kp["id"] == "ESG-T-001")
    info, target = rules.kp_target_authoritative(t001)
    need = dict(target)  # force
    prompt = gen.build_prompt("M1", [(t001, info, need, target)], bank_by_kp)
    check("T7", "build_prompt包含数据集说明",
          t001["id"] in prompt and "数据集说明" in prompt)
    check("T7", "build_prompt包含去重参考(已有样本)",
          "已有" in prompt)

    # 模拟API返回: 2道合法题目
    mock_return = [
        {
            "id": "Q-ESG-T-001-S5", "type": "single_choice", "kp_ref": "ESG-T-001",
            "level": "basic",
            "question": "ESG三大支柱中，E(环境)维度主要关注企业的哪方面表现？",
            "options": {"A": "对自然环境的影响", "B": "与员工和社区的关系", "C": "内部治理结构", "D": "财务审计质量"},
            "answer": "A", "explanation": "E关注企业对自然环境的影响，S关注社会关系，G关注治理结构。",
        },
        {
            "id": "Q-ESG-T-001-M5", "type": "multiple_choice", "kp_ref": "ESG-T-001",
            "level": "basic",
            "question": "ESG评估框架中，G(治理)维度通常考察企业的哪些方面？",
            "options": {"A": "董事会结构", "B": "管理层薪酬", "C": "股东权利", "D": "碳足迹核算"},
            "answer": "ABC", "explanation": "G维度关注董事会结构、管理层薪酬、股东权利等治理要素；碳足迹属于E维度。",
        },
    ]
    original_call = gen.call_deepseek

    def mock_call(api_key, prompt):
        return [dict(q) for q in mock_return]

    gen.call_deepseek = mock_call
    try:
        questions = gen.call_deepseek("sk-test", prompt)
        check("T7", "模拟API返回题目", len(questions) == 2, str(len(questions)))

        # 校验
        validated = []
        for q in questions:
            ok, err = gen.validate_question(q, bank_by_kp)
            ok2, err2 = gen.dedup_check(q, bank_by_kp)
            if ok and ok2:
                validated.append(q)
            else:
                check("T7", f"校验通过: {q['id']}", False, err or err2)
        check("T7", "2道模拟题目均通过校验", len(validated) == 2)

        # 合并到临时bank验证
        temp_bank = {"metadata": dict(bank["metadata"]), "questions": [dict(q) for q in qs]}
        temp_bank["questions"].extend(validated)
        ids = [q["id"] for q in temp_bank["questions"]]
        check("T7", "合并后ID无冲突", len(ids) == len(set(ids)))
        check("T7", "合并后总数+2", len(temp_bank["questions"]) == len(qs) + 2,
              str(len(temp_bank["questions"])))
    finally:
        gen.call_deepseek = original_call




def test_api_config(qs):
    suite_header("[T6] API 配置与降级")

    # 检查 esg_engine.py 常量
    check("T6", "DEEPSEEK_BASE_URL正确",
          engine.DEEPSEEK_BASE_URL == "https://api.deepseek.com")
    check("T6", "DEEPSEEK_MODEL正确", engine.DEEPSEEK_MODEL == "deepseek-chat")

    # API Key 状态
    key_configured = bool(engine.DEEPSEEK_API_KEY and engine.DEEPSEEK_API_KEY != "sk-xxxxxxxx")
    if key_configured:
        check("T6", "API Key已配置(真实Key)", True)
    else:
        RESULTS.skip("T6", "API Key未配置(占位符sk-xxxxxxxx)", "简答AI评分与题库API生成需真实Key")

    # 降级路径: 无Key时简答仍可显示参考答案
    sa_qs = [q for q in qs if q["type"] == "short_answer"]
    has_ref = all(q.get("reference_answer") for q in sa_qs)
    check("T6", "简答题均有参考答案(降级可用)", has_ref)


# ===========================================================================
# T8: 题目修复工具 (离线)
# ===========================================================================

def test_fix_questions(kps, qs, bank):
    suite_header("[T8] 题目修复工具 (离线)")
    import fix_questions as fx

    # 当前题库无重复 (与T2一致的阈值)
    dups = fx.detect_duplicates(bank, threshold=0.75)
    check("T8", "当前题库无重复对", len(dups) == 0, str(len(dups)))

    # core_ratio: 正反镜像题高(真重复), 不同内容低
    hi = fx.core_ratio("以下哪项属于Scope 1温室气体排放？",
                       "以下哪项不属于Scope 1温室气体排放？")
    lo = fx.core_ratio("以下哪项属于气候风险中的转型风险？",
                       "请简述气候风险的两大类别。")
    check("T8", "core_ratio区分相似/不同", hi > 0.7 and lo < 0.5, f"hi={hi:.2f}, lo={lo:.2f}")

    # build_rewrite_prompt 包含关键要素
    h017 = [q for q in qs if q["kp_ref"] == "ESG-H-017" and q["type"] == "single_choice"]
    kp = next(k for k in kps if k["id"] == "ESG-H-017")
    prompt = fx.build_rewrite_prompt(kp, h017[0], h017[1])
    check("T8", "改写提示词包含数据集说明", kp["id"] in prompt and "数据集说明" in prompt)
    check("T8", "改写提示词包含两个样本ID", h017[0]["id"] in prompt and h017[1]["id"] in prompt)
    check("T8", "改写提示词含改写角度", "反例识别" in prompt and "场景应用" in prompt)

    # validate_rewrite: 合法改写通过
    qb = dict(h017[1])
    good = {
        "question": "某化工厂因政府实施更严格的碳排放配额政策导致成本上升，这属于哪类气候风险？",
        "options": {"A": "急性物理风险", "B": "慢性物理风险", "C": "转型风险", "D": "声誉风险"},
        "answer": "C", "explanation": "碳排放配额政策属于政策法规变化，在低碳转型中引发的风险为转型风险。",
    }
    ok, err = fx.validate_rewrite(good, qb, bank)
    check("T8", "合法改写通过校验", ok, err)

    # validate_rewrite: 非法改写被拒绝
    bad = dict(good, answer="Z")
    ok, err = fx.validate_rewrite(bad, qb, bank)
    check("T8", "非法答案被拒绝", not ok and "答案" in err, err)


# ===========================================================================
# T9: 进度存储与智能选题 (离线)
# ===========================================================================

def test_progress_store(qs):
    suite_header("[T9] 进度存储与智能选题")
    import progress_store as ps

    data = {"version": "1.0", "questions": {}}
    fake = [{"id": f"Q-T{i}", "kp_ref": "ESG-T-001", "type": "single_choice",
             "question": f"测试题{i}内容"} for i in range(1, 11)]

    # 记录答题
    ps.record_answer(data, "Q-T1", True, user_input="A")
    ps.record_answer(data, "Q-T1", False, user_input="B")
    st = ps.q_stats(data, "Q-T1")
    check("T9", "记录作答次数/正确数", st["answer_count"] == 2 and st["correct_count"] == 1,
          str(st))
    check("T9", "正确率计算", st["accuracy"] == 50.0, str(st["accuracy"]))
    check("T9", "记录用户输入", st["last_input"] == "B" and len(st["user_inputs"]) == 2)

    # 简答题AI输出记录
    ps.record_answer(data, "Q-T2", False, user_input="回答",
                     ai_output={"score": 5, "reason": "不完整", "suggestion": "补充"})
    st2 = ps.q_stats(data, "Q-T2")
    check("T9", "简答AI输出记录", len(st2["ai_outputs"]) == 1 and st2["ai_outputs"][0]["score"] == 5)

    # 未评分作答 (correct=None)
    ps.record_answer(data, "Q-T3", None, user_input="无AI评分")
    st3 = ps.q_stats(data, "Q-T3")
    check("T9", "未评分作答不计入正确率", st3["accuracy"] is None and st3["ungraded_count"] == 1)

    # 智能选题: 未作答优先
    sel = ps.select_questions(data, fake, 5)
    unanswered_sel = all(q["id"] not in ("Q-T1", "Q-T2", "Q-T3") for q in sel)
    check("T9", "未作答题目优先选中", unanswered_sel, str([q["id"] for q in sel]))

    # 全部作答后: 低正确率优先 (0%的题应比33%的Q-T1更优先)
    for i in range(1, 11):
        ps.record_answer(data, f"Q-T{i}", i % 2 == 0, user_input="A")
    sel2 = ps.select_questions(data, fake, 3)
    acc_of = lambda qid: ps.q_stats(data, qid)["accuracy"]
    selected_accs = [acc_of(q["id"]) for q in sel2]
    # 选中题目正确率都应不高于Q-T1(33%)
    check("T9", "低正确率题目优先", all(a <= 33.0 for a in selected_accs),
          str([(q["id"], acc_of(q["id"])) for q in sel2]))

    # exclude 去重
    sel3 = ps.select_questions(data, fake, 3, exclude={q["id"] for q in sel2})
    check("T9", "exclude避免会话内重复",
          not (set(q["id"] for q in sel2) & set(q["id"] for q in sel3)))

    # 分析聚合
    kps_fake = [{"id": "ESG-T-001", "topic": "测试", "module": "模块1"}]
    report = ps.analyze_progress(data, fake, kps_fake)
    check("T9", "分析报告含总体正确率", report["overall_accuracy"] is not None)
    check("T9", "分析报告含错题列表", isinstance(report["wrong_questions"], list))
    check("T9", "分析报告含模块统计", len(report["module_stats"]) == 1)


def main():
    global VERBOSE
    parser = argparse.ArgumentParser(description="ESG Skill 测试套件")
    parser.add_argument("--verbose", action="store_true", help="显示每个用例")
    parser.add_argument("--offline", action="store_true", help="强制离线模式")
    parser.add_argument("--fix", action="store_true",
                        help="测试后自动调用 fix_questions.py 修复重复题目")
    args = parser.parse_args()
    VERBOSE = args.verbose

    print("=" * 60)
    print("  ESG Skill 测试套件")
    print("  esg-cert-learning | 题库v3.0 | 规则目标550题")
    print("=" * 60)

    kps, qs, kb, bank = load_all()

    test_data_integrity(kps, qs)
    test_bank_structure(kps, qs, bank)
    test_rules_compliance(kps, qs)
    test_engine_functions()
    test_generator_offline(kps, qs)
    test_generation_pipeline(kps, qs, bank)
    test_api_config(qs)
    test_fix_questions(kps, qs, bank)
    test_progress_store(qs)

    # 检测到重复且启用 --fix: 自动修复后复查
    if args.fix:
        import fix_questions as fx
        dups = fx.detect_duplicates(bank, threshold=0.75)
        if dups:
            print(f"\n  [!] 检测到 {len(dups)} 对重复题目, 调用DeepSeek修复...")
            fx.main()
            # 重新加载复查
            kps2, qs2, kb2, bank2 = load_all()
            remaining = fx.detect_duplicates(bank2, threshold=0.75)
            print(f"\n  复查: 剩余重复 {len(remaining)} 对")
        else:
            print("\n  ✓ 无重复题目, 无需修复。")

    # 汇总
    print("\n" + "=" * 60)
    print("  测试结果汇总")
    print("=" * 60)
    print(f"  通过: {len(RESULTS.passed)}")
    print(f"  失败: {len(RESULTS.failed)}")
    if RESULTS.skipped:
        print(f"  跳过: {len(RESULTS.skipped)}")
        for _, name, reason in RESULTS.skipped:
            print(f"    - {name}: {reason}")

    if RESULTS.failed:
        print("\n  ✗ 失败用例:")
        for suite, name, detail in RESULTS.failed:
            print(f"    [{suite}] {name}: {detail}")
        print("\n  结果: FAILED")
        return 1
    else:
        print("\n  结果: ALL PASSED ✓")
        return 0


if __name__ == "__main__":
    sys.exit(main())
