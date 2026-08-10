#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Progress Store (学习进度存储与智能选题)
========================================
记录每次答题情况: 作答次数、正确次数、用户输入、简答题的AI评分输出。
生成每日学习脚本时按进度智能选题, 避免重复抽题或总抽到高正确率题目。

数据文件: progress.json (与题库同目录)
结构:
{
  "version": "1.0",
  "questions": {
    "Q-ESG-T-001-S1": {
      "answer_count": 5, "correct_count": 3,
      "last_result": true, "last_input": "B",
      "user_inputs": [...], "ai_outputs": [{score, reason, suggestion}]
    }
  },
  "last_session": "2026-08-10"
}
"""

import os
import json
import random
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROGRESS_PATH = os.path.join(BASE_DIR, "progress.json")
# 开源版: 数据与脚本同目录(首次运行skill时自动生成)
SKILL_PROGRESS_PATH = os.path.join(BASE_DIR, "progress.json")


def load_progress(path=None):
    """加载进度数据。文件不存在时返回空结构。"""
    path = path or PROGRESS_PATH
    default = {"version": "1.0", "questions": {}, "last_session": None}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("version", "1.0")
        data.setdefault("questions", {})
        return data
    except Exception:
        return default


def save_progress(data, path=None):
    """保存进度到运行目录与skill references两处。"""
    path = path or PROGRESS_PATH
    data["last_session"] = date.today().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        with open(SKILL_PROGRESS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def record_answer(data, q_id, correct, user_input=None, ai_output=None):
    """记录一次答题结果。correct: True/False/None(未评分,如无AI时简答)。
    ai_output 为简答题的 {'score':..,'reason':..,'suggestion':..}。"""
    q = data["questions"].setdefault(q_id, {
        "answer_count": 0, "correct_count": 0, "ungraded_count": 0,
        "last_result": None, "last_input": None,
        "user_inputs": [], "ai_outputs": [],
    })
    q["answer_count"] += 1
    if correct is None:
        q["ungraded_count"] = q.get("ungraded_count", 0) + 1
    elif correct:
        q["correct_count"] += 1
    q["last_result"] = None if correct is None else bool(correct)
    if user_input is not None:
        q["last_input"] = user_input
        q["user_inputs"].append(user_input)
        if len(q["user_inputs"]) > 50:
            q["user_inputs"] = q["user_inputs"][-50:]
    if ai_output is not None:
        q["ai_outputs"].append(ai_output)
        if len(q["ai_outputs"]) > 20:
            q["ai_outputs"] = q["ai_outputs"][-20:]
    return q


def q_stats(data, q_id):
    """返回题目统计 dict。正确率仅按已评分作答计算。"""
    q = data["questions"].get(q_id, {})
    ac = q.get("answer_count", 0)
    cc = q.get("correct_count", 0)
    ug = q.get("ungraded_count", 0)
    graded = ac - ug
    acc = (cc / graded * 100) if graded > 0 else None
    return {
        "answer_count": ac, "correct_count": cc, "ungraded_count": ug,
        "accuracy": acc,
        "last_result": q.get("last_result"), "last_input": q.get("last_input"),
        "user_inputs": q.get("user_inputs", []),
        "ai_outputs": q.get("ai_outputs", []),
    }


def _score(qid, q, questions, now_weight=0.5):
    """选题排序得分: 得分越低越优先复习。
    维度: 未作答(优先) / 正确率(低优先) / 作答次数(少优先) / 最近未答(优先)
    """
    ac = q.get("answer_count", 0)
    cc = q.get("correct_count", 0)
    ug = q.get("ungraded_count", 0)
    graded = ac - ug

    # 1. 未作答: 最高优先级
    if ac == 0:
        return -100.0

    acc = cc / graded if graded > 0 else 0.0
    # 2. 正确率因子: 正确率越高得分越高(越不优先), 低正确率题目优先复习
    acc_factor = acc * 2.0
    # 3. 作答次数因子, 次数越多得分越高(降低优先级, 避免总抽已练熟的题)
    count_factor = min(ac / 20.0, 1.0) * 0.4
    # 4. 上次结果因子, 上次答错更优先
    last_factor = 0.0 if q.get("last_result") is False else 0.15
    # 5. 随机抖动(保证每次选择有变化)
    jitter = random.uniform(0, 0.08)
    return acc_factor + count_factor + last_factor + jitter


def select_questions(data, questions, limit, exclude=None, randomize_first=True):
    """按进度智能选题, 避免重复抽题/高正确率题。
    questions: 候选题目列表
    limit: 需要选出的数量
    exclude: 本会话已用题目ID集合
    返回: 选中题目列表
    """
    exclude = exclude or set()
    candidates = [q for q in questions if q.get("id") not in exclude]

    # 未作答的题: 如果随机优先, 打乱顺序保证每天不同的题
    unanswered = [q for q in candidates if data["questions"].get(q["id"], {}).get("answer_count", 0) == 0]
    answered = [q for q in candidates if data["questions"].get(q["id"], {}).get("answer_count", 0) > 0]

    selected = []
    if randomize_first:
        random.shuffle(unanswered)

    # 1) 优先未作答
    if len(unanswered) >= limit:
        return unanswered[:limit]

    selected = list(unanswered)
    remaining = limit - len(selected)

    # 2) 已回答的按得分排序(低分=薄弱, 优先)
    scored = sorted(answered, key=lambda q: _score(q["id"], data["questions"].get(q["id"], {}), None))
    selected.extend(scored[:remaining])
    return selected


def analyze_progress(data, questions, kps):
    """汇总学习情况, 用于生成分析报告。
    返回 dict: 总体统计、模块统计、知识点统计、错题列表。
    """
    q_by_id = {q["id"]: q for q in questions}
    kp_by_id = {kp["id"]: kp for kp in kps}

    # 总体
    answered_ids = [qid for qid, st in data["questions"].items() if st.get("answer_count", 0) > 0 and qid in q_by_id]
    total_answers = sum(data["questions"][qid]["answer_count"] for qid in answered_ids)
    total_correct = sum(data["questions"][qid]["correct_count"] for qid in answered_ids)

    # 知识点统计
    kp_stats = {}
    for qid in answered_ids:
        q = q_by_id[qid]
        kp_ref = q.get("kp_ref", "unknown")
        st = data["questions"][qid]
        ks = kp_stats.setdefault(kp_ref, {
            "id": kp_ref, "topic": kp_by_id.get(kp_ref, {}).get("topic", kp_ref),
            "module": kp_by_id.get(kp_ref, {}).get("module", ""),
            "answer_count": 0, "correct_count": 0, "ungraded_count": 0,
            "question_ids": [],
        })
        ks["answer_count"] += st["answer_count"]
        ks["correct_count"] += st["correct_count"]
        ks["ungraded_count"] += st.get("ungraded_count", 0)
        ks["question_ids"].append(qid)

    for ks in kp_stats.values():
        graded = ks["answer_count"] - ks["ungraded_count"]
        ks["accuracy"] = (ks["correct_count"] / graded * 100) if graded > 0 else None

    # 模块统计
    module_stats = {}
    for ks in kp_stats.values():
        mod = ks["module"]
        ms = module_stats.setdefault(mod, {
            "module": mod, "answer_count": 0, "correct_count": 0, "kp_count": 0,
        })
        ms["answer_count"] += ks["answer_count"]
        ms["correct_count"] += ks["correct_count"]
        ms["kp_count"] += 1
    for ms in module_stats.values():
        ms["accuracy"] = (ms["correct_count"] / ms["answer_count"] * 100) if ms["answer_count"] else None

    # 错题列表 (正确率<70%或最近答错, 按薄弱程度排序)
    wrong_questions = []
    for qid in answered_ids:
        st = data["questions"][qid]
        q = q_by_id[qid]
        ac = st["answer_count"]
        ug = st.get("ungraded_count", 0)
        graded = ac - ug
        acc = (st["correct_count"] / graded) if graded > 0 else 1.0
        if acc < 0.7 or st.get("last_result") is False:
            wrong_questions.append({
                "id": qid, "question": q.get("question", ""),
                "type": q.get("type", ""), "answer": q.get("answer", ""),
                "explanation": q.get("explanation", ""),
                "answer_count": ac, "correct_count": st["correct_count"],
                "accuracy": acc * 100,
                "kp_ref": q.get("kp_ref", ""),
                "last_input": st.get("last_input"),
                "last_ai": (st.get("ai_outputs") or [None])[-1],
            })
    wrong_questions.sort(key=lambda w: (w["accuracy"], -w["answer_count"]))

    return {
        "answered_questions": len(answered_ids),
        "total_answers": total_answers,
        "total_correct": total_correct,
        "overall_accuracy": (total_correct / total_answers * 100) if total_answers else None,
        "kp_stats": kp_stats,
        "module_stats": module_stats,
        "wrong_questions": wrong_questions[:50],
    }
