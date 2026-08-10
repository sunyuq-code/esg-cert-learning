#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Explanation Generator via DeepSeek API (题目解析生成器)
========================================================
每次生成每日学习脚本前运行, 为题库中解析缺失或过短的题目调用 DeepSeek
大模型, 结合对应知识点的内容生成解析, 使脚本运行时错题可自动显示解析。

用法:
  python generate_explanations.py             # 仅检测缺解析题目
  python generate_explanations.py --generate  # 生成并更新解析
  python generate_explanations.py --force     # 为所有题目重新生成解析
  python generate_explanations.py --min-len 60 # 解析长度阈值(默认40)

API Key 读取顺序: 环境变量 DEEPSEEK_API_KEY > config.md > esg_engine.py
"""

import os
import sys
import json
import re
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANK_PATH = os.path.join(BASE_DIR, "question_bank.json")
KB_PATH = os.path.join(BASE_DIR, "knowledge_base.json")
# 开源版: 数据与脚本同目录
SKILL_BANK_PATH = os.path.join(BASE_DIR, "question_bank.json")
SKILL_CONFIG_PATH = os.path.join(BASE_DIR, "config.md")
ENGINE_PATH = os.path.join(BASE_DIR, "esg_engine.py")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


def resolve_api_key():
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


def find_questions_needing_explanation(bank, min_len=40):
    """找出解析缺失或过短的题目。"""
    return [q for q in bank["questions"]
            if not q.get("explanation") or len(q["explanation"]) < min_len]


def build_prompt(kp, q):
    """构建解析生成提示词: 知识点详解 + 题目 + 答案 -> 生成解析。"""
    qtype = q.get("type", "")
    type_hint = {
        "single_choice": "指出正确答案为何正确、其他选项为何错误",
        "multiple_choice": "逐一说明各正确选项成立的原因, 并说明错误选项不成立的原因",
        "true_false": "说明判断的依据, 若为False指出正确表述",
        "short_answer": "概括回答要点和得分关键, 帮助考生对照检查",
    }.get(qtype, "解释考点与正确答案的依据")

    lines = []
    lines.append("你是ESG认证考试题库解析撰写专家。请为以下考试题目撰写一段简洁清晰的解析。")
    lines.append("")
    lines.append(f"## 对应知识点: {kp.get('id','')} — {kp.get('topic','')}")
    lines.append(f"知识点详解: {kp.get('explanation','')}")
    lines.append("")
    lines.append(f"## 题目 [{qtype}]")
    lines.append(f"题干: {q.get('question','')}")
    if isinstance(q.get("options"), dict):
        for k, v in q["options"].items():
            lines.append(f"  {k}. {v}")
    lines.append(f"答案: {q.get('answer','')}")
    if q.get("reference_answer"):
        lines.append(f"参考答案: {q.get('reference_answer','')[:200]}")
    lines.append("")
    lines.append("## 要求")
    lines.append(f"1. 写一段解析, 重点: {type_hint}")
    lines.append("2. 长度60-150字, 简明扼要, 不重复题干")
    lines.append("3. 基于知识点详解, 确保准确")
    lines.append('4. 输出JSON: {"explanation": "解析内容"}')
    lines.append("5. 只输出JSON, 不要输出其他文字")
    return "\n".join(lines)


def call_deepseek(api_key, prompt):
    """调用 DeepSeek 生成解析, 返回解析文本。"""
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": "你是ESG考试题库解析撰写专家, 严格按照JSON格式输出。"},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        max_tokens=800,
        temperature=0.5,
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("explanation", "").strip()


def main():
    parser = argparse.ArgumentParser(description="DeepSeek 题目解析生成器")
    parser.add_argument("--generate", action="store_true", help="生成并更新解析")
    parser.add_argument("--force", action="store_true", help="为所有题目重新生成解析")
    parser.add_argument("--min-len", type=int, default=40, help="解析长度阈值(默认40)")
    parser.add_argument("--preview", type=int, default=0, help="生成N条预览(不保存)")
    args = parser.parse_args()

    with open(BANK_PATH, "r", encoding="utf-8") as f:
        bank = json.load(f)
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)
    kp_map = {kp["id"]: kp for kp in (kb.get("knowledge_points") if isinstance(kb, dict) else kb)}

    if args.force:
        targets = bank["questions"]
    else:
        targets = find_questions_needing_explanation(bank, args.min_len)

    print("=" * 60)
    print("  题目解析生成器 (DeepSeek API)")
    print("=" * 60)
    print(f"  需生成解析的题目: {len(targets)} (阈值{args.min_len}字)")
    if not targets:
        print("\n  ✓ 所有题目均有完整解析, 无需生成。")
        return 0

    api_key = resolve_api_key()
    if args.preview > 0:
        if not api_key:
            print("  [错误] 未找到DeepSeek API Key")
            return 1
        print(f"\n  [Preview] 生成{args.preview}条测试...")
        for q in targets[:args.preview]:
            kp = kp_map.get(q.get("kp_ref", ""), {})
            prompt = build_prompt(kp, q)
            try:
                exp = call_deepseek(api_key, prompt)
                print(f"    ✓ {q['id']}: {exp[:50]}...")
            except Exception as e:
                print(f"    ✗ {q['id']}: {str(e)[:80]}")
        return 0

    if not args.generate:
        for q in targets[:20]:
            print(f"  - {q['id']} [{q['type']}] 现有解析{len(q.get('explanation',''))}字")
        print("\n  提示: 使用 --generate 生成并更新; --preview N 测试API; --force 全量。")
        return 0

    if not api_key:
        print("  [错误] 未找到DeepSeek API Key!")
        print("  设置: ①export DEEPSEEK_API_KEY=sk-xxx ②config.md ③esg_engine.py")
        return 1

    print(f"\n  正在调用DeepSeek生成 {len(targets)} 条解析...")
    updated = 0
    for i, q in enumerate(targets, 1):
        kp = kp_map.get(q.get("kp_ref", ""), {})
        prompt = build_prompt(kp, q)
        print(f"  [{i}/{len(targets)}] {q['id']} ...", end=" ")
        try:
            exp = call_deepseek(api_key, prompt)
            if len(exp) >= args.min_len:
                q["explanation"] = exp
                updated += 1
                print(f"✓ ({len(exp)}字)")
            else:
                print(f"✗ 生成过短({len(exp)}字)")
        except Exception as e:
            print(f"✗ {str(e)[:60]}")

    # 保存两处
    bank["metadata"]["last_updated"] = "2026-08-10"
    with open(BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)
    with open(SKILL_BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print(f"\n  ✓ 更新 {updated}/{len(targets)} 条解析")
    print(f"  ✓ 题库已保存并同步")

    # 复查
    remaining = find_questions_needing_explanation(bank, args.min_len)
    if remaining:
        print(f"  [!] 仍有 {len(remaining)} 条解析不足, 可再次运行。")
        return 1
    print("  ✓ 复查通过: 所有题目解析完整。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
