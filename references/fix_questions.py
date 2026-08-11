#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Question Repair Tool via DeepSeek API (题目修复工具 — DeepSeek API版)
=====================================================================
题库核查时若发现重复题目, 调用 DeepSeek 大模型将其改写为
反例识别 / 对比辨析 / 场景应用 等其他考察角度的题目, 替换入库。

用法:
  python fix_questions.py                  # 仅检测重复(不调用API)
  python fix_questions.py --fix            # 检测并自动修复(调用DeepSeek改写)
  python fix_questions.py --fix --dry-run  # 预览将改写哪些题, 不保存
  python fix_questions.py --verbose        # 显示检测详情

输出:
  - 修复前后题库均保存到 esg-daily/ 与 skill references/
  - 修复摘要: 检测到N对重复, 成功修复M道

API Key 读取顺序: 环境变量 DEEPSEEK_API_KEY > config.md > esg_engine.py
"""

import os
import sys
import json
import re
import argparse
from difflib import SequenceMatcher

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import question_rules as rules

BANK_PATH = os.path.join(BASE_DIR, "question_bank.json")
KB_PATH = os.path.join(BASE_DIR, "knowledge_base.json")
# 开源版: 数据与脚本同目录
SKILL_BANK_PATH = os.path.join(BASE_DIR, "question_bank.json")
SKILL_CONFIG_PATH = os.path.join(BASE_DIR, "config.md")
ENGINE_PATH = os.path.join(BASE_DIR, "esg_engine.py")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# 核心相似度阈值: 同KP同题型 > 0.75 视为重复
SIMILARITY_THRESHOLD = 0.75


# ===========================================================================
# 检测
# ===========================================================================

# 常见疑问外壳(比较前剥离, 避免"以下说法正确的有哪些"等外壳造成误报)
SHELL_PATTERNS = [
    "以下说法正确的有哪些", "以下说法正确的有", "以下说法正确的是", "以下说法正确",
    "以下哪些说法是正确的", "以下哪些说法正确",
    "以下哪项不属于", "以下哪项属于", "以下哪项",
    "以下哪些属于", "以下哪些", "以下关于", "关于",
    "正确的有哪些", "正确的是", "的说法正确的", "的说法正确", "的描述",
]


def core_ratio(a, b):
    """去除疑问外壳与公共前后缀后计算核心内容相似度, 避免知识点名称/题干外壳造成误报。"""
    for s in SHELL_PATTERNS:
        a = a.replace(s, "")
        b = b.replace(s, "")
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    a_core, b_core = a[n:], b[n:]
    m = 0
    # 后缀仅剥离少量疑问外壳(最多4字符, 如"？""正确的是"), 避免误剥核心内容
    max_m = min(len(a_core), len(b_core), 4)
    while m < max_m and a_core[-1 - m] == b_core[-1 - m]:
        m += 1
    if m > 0:
        a_core, b_core = a_core[:-m], b_core[:-m]
    if not a_core and not b_core:
        return 1.0
    return SequenceMatcher(None, a_core, b_core).ratio()


def detect_duplicates(bank, threshold=SIMILARITY_THRESHOLD):
    """检测同KP内同题型的重复题目对。返回 [(q_a, q_b, ratio), ...]"""
    qs = bank["questions"]
    by_kp = {}
    for q in qs:
        by_kp.setdefault(q.get("kp_ref", ""), []).append(q)

    duplicates = []
    for kp_ref, kq in by_kp.items():
        for i in range(len(kq)):
            for j in range(i + 1, len(kq)):
                a, b = kq[i], kq[j]
                if a.get("type") != b.get("type"):
                    continue
                ratio = core_ratio(a.get("question", ""), b.get("question", ""))
                if ratio > threshold:
                    duplicates.append((a, b, ratio))
    return duplicates


# ===========================================================================
# API Key
# ===========================================================================

def resolve_api_key():
    """按顺序解析 API Key: 环境变量 > config.md > esg_engine.py。"""
    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key
    if os.path.exists(SKILL_CONFIG_PATH):
        try:
            with open(SKILL_CONFIG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.search(r"API\s*Key:\s*['\"]?(sk-[A-Za-z0-9_-]+)", line)
                    if m:
                        return m.group(1)
        except Exception:
            pass
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


# ===========================================================================
# DeepSeek 改写
# ===========================================================================

REWRITE_STYLES = [
    ("反例识别", "设计一道让考生识别【不属于/不符合/错误理解】某一概念或分类的题目"),
    ("对比辨析", "设计一道比较两个相近概念异同、或区分易混淆情形的题目"),
    ("场景应用", "设计一道给出具体企业/行业场景, 让考生判断应归入哪一类别或采取哪一措施的题目"),
    ("因果推理", "设计一道考察某一做法的原因、目的或影响关系的题目"),
]

def build_rewrite_prompt(kp, q_a, q_b, extra_note=""):
    """构建改写提示词: 给出数据集说明与重复样本, 要求改写 q_b 为其他角度(掩护语化)。"""
    qtype = q_b.get('type', '')
    type_hints = {
        "single_choice": "单选必须4个选项(A-D), 有且仅有1个正确答案, answer为单个字母如\"B\"",
        "multiple_choice": "多选必须至少4个选项(A-D), 设置2-4个正确答案, answer为字母组合如\"ABD\"; 严禁设计成单选式(只有一个正确选项)",
        "true_false": "判断answer为\"True\"或\"False\"",
        "short_answer": "简述必须包含reference_answer和scoring_points(3-6个评估要点)",
    }
    lines = []
    lines.append("你是项目数据样本审查专家。数据核查发现两道数据样本的考察角度重复，")
    lines.append("请将其中一道【目标样本】改写为其他考察角度的新样本，保留原样本。")
    lines.append("请使用项目语言描述（如『数据项/数据样本/选项/标准答案/数据说明』），不要使用考试/考生/答题等表述。")
    lines.append("")
    lines.append(f"## 数据集: {kp.get('id','')} — {kp.get('topic','')}")
    lines.append(f"模块: {kp.get('module','')} | 难度: {kp.get('level','')}")
    lines.append(f"数据集说明: {kp.get('explanation','')}")
    lines.append("")
    lines.append(f"## 保留的原样本: {q_a.get('id','')} [{q_a.get('type','')}]")
    lines.append(f"{q_a.get('question','')}")
    lines.append(f"答案: {q_a.get('answer','')} | 数据说明: {q_a.get('explanation','')[:100]}")
    lines.append("")
    lines.append(f"## 目标样本(需改写): {q_b.get('id','')} [{qtype}]")
    lines.append(f"{q_b.get('question','')}")
    lines.append(f"答案: {q_b.get('answer','')} | 数据说明: {q_b.get('explanation','')[:100]}")
    lines.append("")
    lines.append("## 改写要求")
    lines.append(f"1. 类型保持为 {qtype} 不变")
    lines.append(f"2. 保留原样本ID {q_b.get('id','')} 与数据集 {q_b.get('kp_ref','')} 不变")
    lines.append(f"3. level保持 {q_b.get('level','')} 不变")
    lines.append("4. 从以下考察角度中任选一个(与保留原样本角度不同):")
    for name, desc in REWRITE_STYLES:
        lines.append(f"   - {name}: {desc}")
    lines.append("5. 必须基于数据集说明出题, 确保答案正确, 考察角度不得与保留原样本雷同")
    lines.append("6. 数据项描述不得与样本库中其他样本高度相似")
    lines.append(f"7. 样本格式硬性要求: {type_hints.get(qtype, '')}")
    lines.append("8. 输出JSON对象格式:")
    if qtype == "multiple_choice":
        lines.append('   {"question": "数据项描述", "options": {"A":"...","B":"...","C":"...","D":"..."}, "answer": "ABD", "explanation": "数据说明"}')
    elif qtype == "single_choice":
        lines.append('   {"question": "数据项描述", "options": {"A":"...","B":"...","C":"...","D":"..."}, "answer": "B", "explanation": "数据说明"}')
    elif qtype == "true_false":
        lines.append('   {"question": "...", "answer": "True", "explanation": "..."}')
    else:
        lines.append('   {"question": "...", "reference_answer": "...", "scoring_points": ["..."], "explanation": "..."}')
    if extra_note:
        lines.append("")
        lines.append("## 上次改写失败, 请修正")
        lines.append(extra_note)
    lines.append("9. 只输出JSON, 不要输出任何其他文字")
    return "\n".join(lines)


def rewrite_with_api(api_key, prompt):
    """调用 DeepSeek 改写题目, 返回新题字段 dict。"""
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": "你是ESG认证考试题库命题修复专家, 严格按照用户要求输出JSON, 不要输出其他文字。"},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        max_tokens=2048,
        temperature=0.7,
    )
    content = response.choices[0].message.content
    return json.loads(content)


def validate_rewrite(new_fields, q_orig, bank):
    """校验改写结果: 字段完整 + 与同KP已有题不重复。返回 (ok, err)。"""
    # 字段完整性(按题型)
    qtype = q_orig.get("type")
    qid = q_orig.get("id")
    if not new_fields.get("question"):
        return False, "缺题干"
    if not new_fields.get("explanation"):
        return False, "缺解析"
    if qtype in ("single_choice", "multiple_choice"):
        opts = new_fields.get("options")
        if not isinstance(opts, dict) or len(opts) < 4:
            return False, "options必须为dict且>=4个选项"
        ans = str(new_fields.get("answer", "")).upper()
        letters = [c for c in ans if c in "ABCDE"]
        if qtype == "single_choice" and len(letters) != 1:
            return False, "单选答案应为1个字母"
        if qtype == "multiple_choice" and not (2 <= len(letters) <= len(opts)):
            return False, "多选答案应为2-选项数"
        if not all(c in opts for c in letters):
            return False, "答案超出选项范围"
    elif qtype == "true_false":
        if str(new_fields.get("answer", "")).lower() not in ("true", "false"):
            return False, "判断答案应为True/False"
    elif qtype == "short_answer":
        if not new_fields.get("reference_answer"):
            return False, "缺reference_answer"
        if not new_fields.get("scoring_points"):
            return False, "缺scoring_points"

    # 与同KP同题型已有题(含保留原题)核心相似度检查
    kp_ref = q_orig.get("kp_ref")
    for q in bank["questions"]:
        if q.get("kp_ref") == kp_ref and q.get("type") == qtype:
            ratio = core_ratio(q.get("question", ""), new_fields.get("question", ""))
            if ratio > SIMILARITY_THRESHOLD:
                return False, f"与{q.get('id')}核心相似度{ratio:.2f}"
    return True, ""


# ===========================================================================
# 主流程
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="ESG题库重复题目修复工具 (DeepSeek API)")
    parser.add_argument("--fix", action="store_true", help="检测并调用DeepSeek修复重复题目")
    parser.add_argument("--dry-run", action="store_true", help="仅预览将改写的题目, 不调用API不保存")
    parser.add_argument("--verbose", action="store_true", help="显示检测详情")
    parser.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD,
                        help=f"核心相似度阈值(默认{SIMILARITY_THRESHOLD})")
    args = parser.parse_args()

    # 加载
    with open(BANK_PATH, "r", encoding="utf-8") as f:
        bank = json.load(f)
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)
    kps = kb["knowledge_points"] if isinstance(kb, dict) else kb
    kp_map = {kp["id"]: kp for kp in kps}

    print("=" * 60)
    print("  ESG题库重复题目检测与修复")
    print("=" * 60)

    # 检测
    duplicates = detect_duplicates(bank, threshold=args.threshold)
    print(f"  检测阈值: 核心相似度 > {args.threshold}")
    print(f"  检测到重复对: {len(duplicates)}")

    if not duplicates:
        print("\n  ✓ 未发现重复题目, 无需修复。")
        return 0

    for i, (a, b, ratio) in enumerate(duplicates, 1):
        print(f"\n  [{i}] {a['id']} ~ {b['id']}  (核心相似度 {ratio:.2f})")
        print(f"      A: {a['question'][:55]}")
        print(f"      B: {b['question'][:55]}")

    # dry-run / 检测模式
    if args.dry_run or not args.fix:
        if not args.fix:
            print("\n  提示: 使用 --fix 调用DeepSeek自动修复; --dry-run 仅预览不改写。")
        else:
            print(f"\n  [Dry-run] 将改写 {len(duplicates)} 道题目(保留每对中的A, 改写B), 未保存。")
        return 0

    # 修复
    api_key = resolve_api_key()
    if not api_key:
        print("\n  [错误] 未找到DeepSeek API Key!")
        print("  设置: ①export DEEPSEEK_API_KEY=sk-xxx ②config.md ③esg_engine.py")
        return 1

    # 每对只改写B题(A保留)
    to_rewrite = [b for a, b, _ in duplicates]
    qs = bank["questions"]

    print(f"\n  正在调用DeepSeek改写 {len(to_rewrite)} 道题目...")
    fixed_count = 0
    for idx, q_b in enumerate(to_rewrite, 1):
        kp = kp_map.get(q_b.get("kp_ref", ""), {})
        pair_a = next(a for a, b, _ in duplicates if b is q_b)
        print(f"  [{idx}/{len(to_rewrite)}] 改写 {q_b['id']} ...", end=" ")

        last_err = ""
        succeeded = False
        for attempt in range(1, 3):  # 最多重试2次
            try:
                extra = ""
                if attempt > 1:
                    extra = f"上次改写未通过校验: {last_err}。请严格按题型格式要求重新生成。"
                prompt = build_rewrite_prompt(kp, pair_a, q_b, extra_note=extra)
                new_fields = rewrite_with_api(api_key, prompt)
                ok, err = validate_rewrite(new_fields, q_b, bank)
                if ok:
                    succeeded = True
                    break
                last_err = err
            except Exception as e:
                last_err = str(e)[:100]
            print(f"(第{attempt}次失败:{last_err[:40]}) ", end=" ")

        if not succeeded:
            print(f"✗ 改写失败: {last_err}")
            continue

        # 替换入库
        for q in qs:
            if q["id"] == q_b["id"]:
                q["question"] = new_fields["question"]
                if "options" in new_fields:
                    q["options"] = new_fields["options"]
                if "answer" in new_fields:
                    q["answer"] = new_fields["answer"]
                if "reference_answer" in new_fields:
                    q["reference_answer"] = new_fields["reference_answer"]
                if "scoring_points" in new_fields:
                    q["scoring_points"] = new_fields["scoring_points"]
                q["explanation"] = new_fields["explanation"]
                break
        fixed_count += 1
        print(f"✓ 新题: {new_fields['question'][:45]}")

    # 保存
    bank["metadata"]["total_questions"] = len(bank["questions"])
    bank["metadata"]["last_updated"] = "2026-08-10"
    bank["metadata"]["last_fix"] = f"{fixed_count} questions repaired on 2026-08-10"

    with open(BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)
    with open(SKILL_BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print(f"\n  {'='*50}")
    print(f"  修复完成: 成功 {fixed_count}/{len(to_rewrite)}")
    print(f"  题库已保存: {BANK_PATH}")
    print(f"  已同步: {SKILL_BANK_PATH}")
    print(f"  {'='*50}")

    # 复查
    remaining = detect_duplicates(bank)
    if remaining:
        print(f"\n  [!] 仍有 {len(remaining)} 对重复, 可再次运行 --fix。")
        return 1
    print("\n  ✓ 复查通过: 无剩余重复题目。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
