#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Question Bank Generator via DeepSeek API (题库生成器 — DeepSeek API版)

功能:
- 读取 knowledge_base.json 与 question_bank.json
- 按 question_rules.py (v3.0 量化规则) 计算每个知识点的目标题型分配
- 与现有题库对比，找出缺失题目
- 调用 DeepSeek API (deepseek-chat, JSON模式) 批量生成缺失题目
- 校验、去重、合并回 question_bank.json (同时同步到 skill references)

用法:
  python generate_questions.py                # 仅检查缺口 (dry-run)
  python generate_questions.py --generate     # 生成并合并缺失题目
  python generate_questions.py --module M2    # 只处理指定模块 (M1/M2/M3/M4/M5a/M5b/all)
  python generate_questions.py --preview 5    # 生成5题预览(不保存,用于测试API)
  python generate_questions.py --force        # 忽略现状,按目标全部补齐

API Key 获取顺序: 环境变量 DEEPSEEK_API_KEY > config.md > esg_engine.py
"""

import os
import sys
import json
import argparse
import re
from collections import Counter

import question_rules as rules

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANK_PATH = os.path.join(BASE_DIR, "question_bank.json")
KB_PATH = os.path.join(BASE_DIR, "knowledge_base.json")
# 开源版: 数据与脚本同目录
SKILL_BANK_PATH = os.path.join(BASE_DIR, "question_bank.json")
SKILL_CONFIG_PATH = os.path.join(BASE_DIR, "config.md")
ENGINE_PATH = os.path.join(BASE_DIR, "esg_engine.py")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_QUESTIONS_PER_CALL = 25  # 单次API调用最大题目数(避免超出max_tokens)


def resolve_api_key():
    """按顺序解析 API Key: 环境变量 > config.md > esg_engine.py。"""
    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key
    # config.md
    if os.path.exists(SKILL_CONFIG_PATH):
        try:
            with open(SKILL_CONFIG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.search(r"API\s*Key:\s*['\"]?(sk-[A-Za-z0-9_-]+)", line)
                    if m:
                        return m.group(1)
        except Exception:
            pass
    # esg_engine.py
    if os.path.exists(ENGINE_PATH):
        try:
            with open(ENGINE_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.search(r"DEEPSEEK_API_KEY\s*=\s*['\"](sk-[A-Za-z0-9_-]+)['\"]", line)
                    if m:
                        return m.group(1)
        except Exception:
            pass
    return ""


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def group_by_module(kps):
    """将知识点按课程模块分组 (M1/M2/M3/M4/M5a/M5b)。"""
    modules = {"M1": [], "M2": [], "M3": [], "M4": [], "M5a": [], "M5b": []}
    for kp in kps:
        kp_id = kp["id"]
        if kp_id.startswith("ESG-T-"):
            modules["M1"].append(kp)
        elif kp_id.startswith("ESG-S-"):
            modules["M2"].append(kp)
        elif kp_id.startswith("ESG-I-"):
            modules["M3"].append(kp)
        elif kp_id.startswith("ESG-R-"):
            modules["M4"].append(kp)
        elif kp_id.startswith("ESG-H-"):
            num = int(kp_id.split("-")[-1])
            modules["M5a" if num <= 12 else "M5b"].append(kp)
    return modules


def build_need_plan(kps, bank_by_kp, force=False):
    """计算每个知识点缺失的题型。返回 [(kp, info, need_dict), ...]"""
    plan = []
    for kp in kps:
        info, target = rules.kp_target_authoritative(kp)
        current = bank_by_kp.get(kp["id"], {})
        if force:
            need = dict(target)  # 全部按目标补齐(会去重/替换)
        else:
            need = rules.missing_questions(current, target)
        if sum(need.values()) > 0:
            plan.append((kp, info, need, target))
    return plan


def next_seq_for_kp(bank_by_kp, kp_id, type_code):
    """计算该KP某题型的下一个序号。"""
    cur = bank_by_kp.get(kp_id, {})
    # 通过ID推断: Q-ESG-T-001-S3 -> seq 3
    max_seq = 0
    type_name = rules.TYPE_NAMES[type_code]
    for q in bank_by_kp.get(kp_id + "_questions", []):
        if q.get("type") == type_name:
            m = re.search(r"-([A-Z])(\d+)$", q.get("id", ""))
            if m and m.group(1) == type_code:
                max_seq = max(max_seq, int(m.group(2)))
    return max_seq + 1


def build_prompt(module_name, kp_groups, bank_by_kp):
    """为一批知识点构建生成提示词(完全使用项目数据样本掩护语)。"""
    lines = []
    lines.append("你是一位项目数据样本生成专家。请根据给定的数据集内容，生成指定数量和类型的高质量数据样本(用于数据审计项目的培训/评审材料)。")
    lines.append("请使用项目语言描述（如『数据样本/数据项/选项/标准答案/数据说明』），不要使用考试/考生/答题等表述。")
    lines.append("")
    lines.append("## 样本格式要求")
    lines.append("")
    lines.append("生成一个JSON对象，格式为：")
    lines.append('{"questions": [样本对象, ...]}')
    lines.append("")
    lines.append("样本对象字段：")
    lines.append('- "id": 样本ID(见下方ID规则)')
    lines.append('- "type": "single_choice" | "multiple_choice" | "true_false" | "short_answer"')
    lines.append('- "kp_ref": 数据集ID')
    lines.append('- "level": "basic" | "intermediate" | "advanced"')
    lines.append('- "question": 数据项描述(题干)')
    lines.append('- "options": 选项对象，如 {"A":"选项文本","B":"选项文本","C":"选项文本","D":"选项文本"}（判断/简述不需要）')
    lines.append('- "answer": 答案。单选为单个字母如"A"；多选为字母组合如"ABC"；判断为"True"/"False"；简述为"reference_answer"字段')
    lines.append('- "explanation": 数据说明(解析)')
    lines.append('- "reference_answer": 标准数据（仅简述）')
    lines.append('- "scoring_points": 评估要点列表（仅简述，3-6个要点）')
    lines.append("")
    lines.append("## ID规则")
    lines.append("ID格式：Q-{数据集ID}-{类型代码}{序号}，类型代码 S=单选 M=多选 T=判断 A=简述。")
    lines.append("例如：Q-ESG-S-001-S4 表示ESG-S-001数据集的第4个单选样本。")
    lines.append("")
    lines.append("## 样本质量要求")
    lines.append("1. 单选4个选项(A-D)，只有一个正确答案")
    lines.append("2. 多选4-5个选项(A-E)，2-4个正确答案")
    lines.append("3. 判断为对/错陈述，答案True或False")
    lines.append("4. 简述需包含完整标准数据和3-6个评估要点")
    lines.append("5. 样本内容必须严格基于给定的数据集说明，确保答案正确")
    lines.append("6. 考察角度必须与【已有样本】不同，避免描述高度相似")
    lines.append("7. 所有文本使用简体中文，不要使用ASCII双引号作为中文引号（用「」或《》）")
    lines.append("")
    lines.append(f"## 本批数据集（模块 {module_name}）")
    lines.append("")

    for kp, info, need, target in kp_groups:
        lines.append(f"### 数据集: {kp['id']} — {kp.get('topic','')}")
        lines.append(f"模块: {kp.get('module','')}")
        lines.append(f"难度: {kp.get('level','')}")
        lines.append(f"数据类型: {info['ct']} | 复杂度总分: {info['total']} | 目标样本量: {target}")
        lines.append(f"数据集说明: {kp.get('explanation','')}")
        lines.append("")
        # 需要生成的题型
        need_items = []
        for tc in ["S", "M", "T", "A"]:
            if need.get(tc, 0) > 0:
                type_name = rules.TYPE_NAMES[tc]
                lines.append(f"- 需要生成 {need[tc]} 道{type_name}（类型代码{tc}）")
                need_items.append(tc)
        lines.append("")
        # 已有样本(去重参考)
        existing = bank_by_kp.get(kp["id"] + "_questions", [])
        if existing:
            lines.append(f"该数据集已有 {len(existing)} 道样本，新样本的考察角度必须不同：")
            for q in existing[:6]:  # 最多展示6道作参考
                lines.append(f"  - [{q.get('type','')}] {q.get('question','')[:60]}")
            if len(existing) > 6:
                lines.append(f"  ...(共{len(existing)}道)")
            lines.append("")
    return "\n".join(lines)


def call_deepseek(api_key, prompt):
    """调用 DeepSeek API 生成题目。返回题目列表。"""
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    system_prompt = (
        "你是项目数据样本生成引擎。严格按照用户要求的JSON格式输出数据样本。"
        "使用项目语言描述, 不使用考试/考生/答题等表述。只输出JSON，不要输出任何其他文字。"
    )

    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        max_tokens=8192,
        temperature=0.7,
    )
    content = response.choices[0].message.content
    data = json.loads(content)
    questions = data.get("questions", [])
    if not questions and isinstance(data, list):
        questions = data
    return questions


def validate_question(q, bank_by_kp):
    """校验单道题目，返回 (ok, error_msg)。"""
    qid = q.get("id", "")
    qtype = q.get("type", "")
    kp_ref = q.get("kp_ref", "")
    if not qid or not qtype or not kp_ref:
        return False, "缺少 id/type/kp_ref 字段"
    # ID格式
    m = re.match(r"^Q-(ESG-[A-Z]-\d{3})-([SMTA])(\d+)$", qid)
    if not m:
        return False, f"ID格式错误: {qid}"
    # kp_ref 与ID一致
    if m.group(1) != kp_ref:
        return False, f"kp_ref({kp_ref})与ID({qid})不一致"
    if not q.get("question"):
        return False, "缺少题干"
    if not q.get("explanation"):
        return False, "缺少解析"
    level = q.get("level", "")
    if level not in ("basic", "intermediate", "advanced"):
        return False, f"level无效: {level}"

    if qtype in ("single_choice", "multiple_choice"):
        opts = q.get("options")
        if not isinstance(opts, dict) or len(opts) < 4:
            return False, "选择题options必须为字典且至少4个选项"
        if qtype == "single_choice":
            ans = q.get("answer", "")
            if len(str(ans).strip()) != 1 or ans.upper() not in opts:
                return False, f"单选答案无效: {ans}"
        else:
            ans = str(q.get("answer", "")).upper()
            letters = [c for c in ans if c in "ABCDE"]
            if len(letters) < 2 or len(letters) > 4:
                return False, f"多选答案需2-4个选项: {ans}"
            if not all(c in opts for c in letters):
                return False, f"多选答案超出选项范围: {ans}"
    elif qtype == "true_false":
        ans = str(q.get("answer", "")).lower()
        if ans not in ("true", "false"):
            return False, f"判断答案需为True/False: {ans}"
    elif qtype == "short_answer":
        if not q.get("reference_answer"):
            return False, "简答题缺少reference_answer"
        if not q.get("scoring_points"):
            return False, "简答题缺少scoring_points"
    else:
        return False, f"未知题型: {qtype}"
    return True, ""


def dedup_check(q, bank_by_kp):
    """检查是否与同KP已有题目重复。返回 (ok, msg)。"""
    kp_ref = q.get("kp_ref", "")
    existing = bank_by_kp.get(kp_ref + "_questions", [])
    qtext = q.get("question", "")
    for eq in existing:
        # 题干前20字符比对，避免同一知识点重复考察相同要点
        if eq.get("question", "")[:20] == qtext[:20] and len(qtext) > 20:
            return False, f"与已有题目题干相似: {eq.get('question','')[:40]}"
    return True, ""


def assign_seq(questions, bank_by_kp):
    """为缺少ID序号的题目分配序号(按题型)。"""
    seq_counter = {}
    for q in questions:
        qid = q.get("id", "")
        m = re.match(r"^Q-(ESG-[A-Z]-\d{3})-([SMTA])(\d+)$", qid)
        if m:
            kp_ref = m.group(1)
            tc = m.group(2)
            key = (kp_ref, tc)
            # 确保序号不与已有题目冲突
            existing_max = 0
            for eq in bank_by_kp.get(kp_ref + "_questions", []):
                em = re.search(r"-([SMTA])(\d+)$", eq.get("id", ""))
                if em and em.group(1) == tc:
                    existing_max = max(existing_max, int(em.group(2)))
            seq_counter.setdefault(key, max(existing_max, int(m.group(3))))
    # 对无序号或重复的ID重新编号
    used_ids = set(q.get("id") for q in bank_by_kp.get("_all_questions", []))
    for q in questions:
        qid = q.get("id", "")
        m = re.match(r"^Q-(ESG-[A-Z]-\d{3})-([SMTA])(\d+)$", qid)
        if not m:
            continue
        if qid in used_ids:
            # 序号冲突，递增
            kp_ref, tc = m.group(1), m.group(2)
            key = (kp_ref, tc)
            seq_counter[key] = seq_counter.get(key, 0) + 1
            new_id = f"Q-{kp_ref}-{tc}{seq_counter[key]}"
            q["id"] = new_id
        used_ids.add(q["id"])
    return questions


def main():
    parser = argparse.ArgumentParser(description="DeepSeek API 题库生成器")
    parser.add_argument("--generate", action="store_true", help="生成并合并缺失题目(默认仅dry-run)")
    parser.add_argument("--module", default="all", help="处理模块: M1/M2/M3/M4/M5a/M5b/all")
    parser.add_argument("--preview", type=int, default=0, help="生成N题预览但不保存(测试API)")
    parser.add_argument("--force", action="store_true", help="忽略现状按目标补齐")
    args = parser.parse_args()

    # 加载数据
    bank = load_json(BANK_PATH)
    kb = load_json(KB_PATH)
    kps = kb["knowledge_points"] if isinstance(kb, dict) else kb
    all_questions = bank["questions"]

    # 建立索引
    bank_by_kp = {}
    for q in all_questions:
        kp_ref = q.get("kp_ref", "")
        bank_by_kp.setdefault(kp_ref, {"S": 0, "M": 0, "T": 0, "A": 0})
        tc = rules.name_to_type_code(q.get("type", ""))
        if tc:
            bank_by_kp[kp_ref][tc] += 1
        bank_by_kp.setdefault(kp_ref + "_questions", []).append(q)
    bank_by_kp["_all_questions"] = all_questions

    # 构建计划
    modules = group_by_module(kps)
    if args.module != "all":
        modules = {args.module: modules.get(args.module, [])}

    total_need = 0
    for mod, mod_kps in modules.items():
        plan = build_need_plan(mod_kps, bank_by_kp, force=args.force)
        for kp, info, need, target in plan:
            total_need += sum(need.values())

    print("=" * 60)
    print(f"  题库生成计划 (DeepSeek API) | 规则 v3.0")
    print("=" * 60)
    print(f"  知识点总数: {len(kps)} | 现有题库: {len(all_questions)}")
    print(f"  规则目标: 550题 | 待生成: {total_need}题")
    print("-" * 60)

    for mod, mod_kps in modules.items():
        plan = build_need_plan(mod_kps, bank_by_kp, force=args.force)
        if not plan:
            print(f"  [{mod}] 无需生成 (已达标)")
            continue
        print(f"\n  [{mod}] 需要生成:")
        for kp, info, need, target in plan:
            desc = ", ".join(f"{rules.TYPE_NAMES[t]}×{n}" for t, n in need.items() if n > 0)
            print(f"    {kp['id']} {kp.get('topic','')}: {desc} (总分{info['total']})")

    # preview 模式: 测试API, 不保存
    if args.preview > 0:
        print(f"\n  [Preview] 生成{args.preview}道题目测试API...")
        api_key = resolve_api_key()
        if not api_key:
            print("  [错误] 未找到DeepSeek API Key!")
            print("  设置方法: ① export DEEPSEEK_API_KEY=sk-xxx")
            print("            ② 在config.md的API Key字段填写")
            print("            ③ 在esg_engine.py的DEEPSEEK_API_KEY填写")
            sys.exit(1)

        # 取第一个需要生成的模块做测试 (preview始终强制构建计划, 不受题库现状影响)
        for mod, mod_kps in modules.items():
            plan = build_need_plan(mod_kps, bank_by_kp, force=True)
            if plan:
                preview_groups = plan[:1]  # 1个KP
                prompt = build_prompt(mod, preview_groups, bank_by_kp)
                print(f"  [Preview] 调用DeepSeek ({DEEPSEEK_MODEL})...")
                try:
                    questions = call_deepseek(api_key, prompt)
                    print(f"  [Preview] API返回 {len(questions)} 道题目")
                    ok_count = 0
                    for q in questions[:args.preview]:
                        ok, err = validate_question(q, bank_by_kp)
                        ok2, err2 = dedup_check(q, bank_by_kp)
                        if ok and ok2:
                            ok_count += 1
                            print(f"    ✓ {q.get('id')} [{q.get('type')}] {q.get('question','')[:40]}")
                        else:
                            print(f"    ✗ {q.get('id')}: {err or err2}")
                    print(f"  [Preview] 校验通过 {ok_count}/{min(len(questions), args.preview)}")
                except Exception as e:
                    print(f"  [错误] API调用失败: {e}")
                return

    # generate 模式
    if args.generate:
        api_key = resolve_api_key()
        if not api_key:
            print("\n  [错误] 未找到DeepSeek API Key! 使用 --preview 可测试API, 配置见上方提示。")
            sys.exit(1)

        if total_need == 0:
            print("\n  题库已达标(≥550题规则目标), 无需生成。")
            print("  如需强制补齐请加 --force。")
            return

        all_new = []
        print("\n  正在调用DeepSeek API生成题目...")
        for mod, mod_kps in modules.items():
            plan = build_need_plan(mod_kps, bank_by_kp, force=args.force)
            if not plan:
                continue
            # 按批量上限拆分
            for i in range(0, len(plan), MAX_QUESTIONS_PER_CALL // 2):
                batch = plan[i:i + MAX_QUESTIONS_PER_CALL // 2]
                prompt = build_prompt(mod, batch, bank_by_kp)
                print(f"  [{mod}] 调用API (批次 {i//(MAX_QUESTIONS_PER_CALL//2)+1})...")
                try:
                    questions = call_deepseek(api_key, prompt)
                    all_new.extend(questions)
                    print(f"    ✓ 返回 {len(questions)} 道")
                except Exception as e:
                    print(f"    ✗ 失败: {e}")

        # 校验+去重+合并
        print("\n  校验与合并...")
        merged = []
        fail_count = 0
        for q in all_new:
            ok, err = validate_question(q, bank_by_kp)
            ok2, err2 = dedup_check(q, bank_by_kp)
            if ok and ok2:
                merged.append(q)
            else:
                fail_count += 1
                print(f"    ✗ 丢弃 {q.get('id','?')}: {err or err2}")

        merged = assign_seq(merged, bank_by_kp)

        if merged:
            bank["questions"] = all_questions + merged
            bank["metadata"]["total_questions"] = len(bank["questions"])
            bank["metadata"]["rules_version"] = "3.0"
            bank["metadata"]["last_updated"] = "2026-08-10"
            save_json(BANK_PATH, bank)
            save_json(SKILL_BANK_PATH, bank)
            print(f"\n  ✓ 合并完成: {len(all_questions)} + {len(merged)} = {len(bank['questions'])}")
            print(f"  ✓ 已同步到 skill references")
        else:
            print("  ✗ 没有通过校验的题目, 题库未变更。")

        if fail_count:
            print(f"  (丢弃 {fail_count} 道未通过校验的题目)")
    else:
        print("\n  提示: 使用 --generate 实际生成并合并; --preview N 可测试API而不保存。")


if __name__ == "__main__":
    main()
