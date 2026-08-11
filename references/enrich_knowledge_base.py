#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enrich Knowledge Base via DeepSeek (知识库内容丰富工具)
============================================================
扫描 knowledge_base.json 中 explanation 过短的知识点,
调用 DeepSeek 大模型, 基于 topic + concept + 现有内容,
生成 300-500 字的详细数据说明, 同步写入运行目录与 skill references。
GitHub 开源版: 数据与脚本同目录, 单写。
"""

import os
import sys
import json
import argparse
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_PATH = os.path.join(BASE_DIR, "knowledge_base.json")
# 开源版: 数据与脚本同目录
SKILL_KB_PATH = os.path.join(BASE_DIR, "knowledge_base.json")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
MIN_LEN = 200  # 短于200字视为需丰富


def call_deepseek(api_key, prompt):
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": "你是项目数据说明撰写专家。请使用项目语言描述(数据项/数据集说明等), 不要使用考试/考生/答题等表述。"},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        max_tokens=1500,
        temperature=0.5,
    )
    return json.loads(response.choices[0].message.content).get("explanation", "").strip()


def build_prompt(kp):
    return '''请根据以下信息, 为该数据集撰写一段300-500字的详细说明文字(项目数据语言)。

数据集名称: {topic}
核心概念: {concept}
现有简短说明: {expl}

## 要求
1. 输出JSON: {{"explanation": "详细说明"}}
2. 内容应覆盖: 定义/范围/关键要素/方法/标准/最佳实践/常见误区
3. 使用项目数据语言(如『数据项/数据采集/数据治理/质量控制/合规要求』), 不使用考试/考生/答题等表述
4. 长度300-500字
5. 只输出JSON'''.format(
        topic=kp.get('topic', ''),
        concept=kp.get('concept', ''),
        expl=kp.get('explanation', ''),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="限制处理数量(默认全部)")
    parser.add_argument("--start", type=int, default=0, help="起始索引(用于分批)")
    parser.add_argument("--dry-run", action="store_true", help="仅扫描,不调用API")
    args = parser.parse_args()

    with open(KB_PATH, encoding="utf-8") as f:
        kb = json.load(f)
    kps = kb["knowledge_points"]

    targets = [kp for kp in kps if len(kp.get("explanation", "")) < MIN_LEN]
    print(f"扫描: 知识点 {len(kps)} | 需丰富(<{MIN_LEN}字): {len(targets)}")
    if args.start:
        targets = targets[args.start:]
    if args.limit:
        targets = targets[:args.limit]

    if not targets:
        print("✓ 所有知识点均有详细内容, 无需丰富。")
        return 0

    if args.dry_run:
        for kp in targets[:10]:
            print(f"  {kp['id']} {kp['topic']} ({len(kp.get('explanation',''))}字)")
        print(f"  ...(共{len(targets)}项)")
        return 0

    # 解析API Key
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        for path in [
            os.path.join(BASE_DIR, "config.md"),
            os.path.join(BASE_DIR, "esg_engine.py"),
        ]:
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        import re
                        m = re.search(r"DEEPSEEK_API_KEY\s*=\s*['\"](sk-[A-Za-z0-9_-]+)['\"]", line) or re.search(r"API\s*Key:\s*(sk-[A-Za-z0-9_-]+)", line)
                        if m:
                            api_key = m.group(1); break
                if api_key: break
            except Exception:
                pass
    if not api_key:
        print("[错误] 未找到DeepSeek API Key!")
        return 1

    print(f"\n开始丰富 {len(targets)} 个KP...")
    success = 0
    t0 = time.time()
    for i, kp in enumerate(targets, 1):
        old_len = len(kp.get("explanation", ""))
        prompt = build_prompt(kp)
        for attempt in range(1, 3):
            try:
                new_exp = call_deepseek(api_key, prompt)
                if len(new_exp) >= MIN_LEN:
                    kp["explanation"] = new_exp
                    success += 1
                    print(f"  [{i}/{len(targets)}] {kp['id']} {old_len}字 -> {len(new_exp)}字 ✓")
                    break
                else:
                    print(f"  [{i}/{len(targets)}] {kp['id']} 生成过短({len(new_exp)}字), 重试...")
            except Exception as e:
                print(f"  [{i}/{len(targets)}] {kp['id']} 第{attempt}次失败: {str(e)[:60]}")
                time.sleep(1)
        else:
            print(f"  [{i}/{len(targets)}] {kp['id']} 失败, 跳过")

    # 保存两处
    kb["metadata"]["last_updated"] = "2026-08-11"
    with open(KB_PATH, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
    with open(SKILL_KB_PATH, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    print(f"\n✓ 完成: 成功丰富 {success}/{len(targets)} 个KP (耗时{elapsed:.0f}秒)")
    print(f"  已保存: {KB_PATH}")
    print(f"  已同步: {SKILL_KB_PATH}")
    return 0 if success == len(targets) else 1


if __name__ == "__main__":
    sys.exit(main())