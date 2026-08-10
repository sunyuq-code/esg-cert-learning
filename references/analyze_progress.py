#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Progress Analysis Report (学习情况分析报告)
============================================
读取 progress.json(作答记录) + question_bank.json + knowledge_base.json,
生成 HTML 学习分析报告: 总体统计、模块正确率、薄弱知识点、错题列表、复习建议。

触发词: "分析数据表"
用法:
  python analyze_progress.py                # 生成报告 HTML
  python analyze_progress.py --open         # 生成并用默认浏览器打开
  python analyze_progress.py --out report.html
"""

import os
import sys
import json
import html
import argparse
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROGRESS_PATH = os.path.join(BASE_DIR, "progress.json")
BANK_PATH = os.path.join(BASE_DIR, "question_bank.json")
KB_PATH = os.path.join(BASE_DIR, "knowledge_base.json")
DEFAULT_OUT = os.path.join(BASE_DIR, "progress_report.html")


def load():
    progress = {"version": "1.0", "questions": {}}
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            progress = json.load(f)
    with open(BANK_PATH, "r", encoding="utf-8") as f:
        bank = json.load(f)
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)
    kps = kb["knowledge_points"] if isinstance(kb, dict) else kb
    return progress, bank["questions"], kps


def fmt_pct(x):
    return "—" if x is None else f"{x:.1f}%"


def bar_style(acc):
    """按正确率返回进度条颜色。"""
    if acc is None:
        return "#adb5bd"
    if acc >= 80:
        return "#198754"  # 绿
    if acc >= 60:
        return "#ffc107"  # 黄
    return "#dc3545"      # 红


def build_html(report, kps):
    total_answered = report["answered_questions"]
    total_answers = report["total_answers"]
    overall = report["overall_accuracy"]
    wrong_count = len(report["wrong_questions"])

    # 总体卡片
    cards = [
        ("已作答题目", str(total_answered), "题"),
        ("总作答次数", str(total_answers), "次"),
        ("总正确率", fmt_pct(overall), ""),
        ("薄弱知识点", str(len(report["kp_stats"])), "个"),
        ("需复习错题", str(wrong_count), "道"),
    ]

    # 模块
    mod_rows = ""
    for ms in sorted(report["module_stats"].values(), key=lambda m: (m["accuracy"] or 0)):
        acc = ms["accuracy"]
        color = bar_style(acc)
        mod_rows += f"""
        <tr>
          <td class="tl">{html.escape(ms['module'])}</td>
          <td>{ms['kp_count']}</td>
          <td>{ms['answer_count']}</td>
          <td>{fmt_pct(acc)}</td>
          <td class="bar-cell">
            <div class="bar"><div class="bar-fill" style="width:{acc if acc is not None else 0:.0f}%;background:{color}"></div></div>
          </td>
        </tr>"""

    # 知识点排行 (按正确率升序 = 薄弱优先)
    kp_list = sorted(report["kp_stats"].values(), key=lambda k: (k["accuracy"] or 0))
    kp_rows = ""
    for k in kp_list:
        acc = k["accuracy"]
        color = bar_style(acc)
        kp_rows += f"""
        <tr>
          <td class="tl"><span class="mono">{html.escape(k['id'])}</span> {html.escape(k['topic'])}</td>
          <td>{k['answer_count']}</td>
          <td>{fmt_pct(acc)}</td>
          <td class="bar-cell">
            <div class="bar"><div class="bar-fill" style="width:{acc if acc is not None else 0:.0f}%;background:{color}"></div></div>
          </td>
        </tr>"""

    # 错题
    wrong_rows = ""
    for w in report["wrong_questions"]:
        last_ai = w.get("last_ai") or {}
        ai_block = ""
        if last_ai.get("score") is not None:
            sc = last_ai["score"]
            ai_block = f"""
            <div class="ai-box">
              <b>AI评分: {sc}/10</b> — {html.escape(str(last_ai.get('reason',''))[:120])}
              {('<div class="sug">建议: ' + html.escape(str(last_ai.get('suggestion',''))[:100]) + '</div>') if last_ai.get('suggestion') else ''}
            </div>"""
        type_label = {"single_choice": "单选", "multiple_choice": "多选",
                      "true_false": "判断", "short_answer": "简答"}.get(w["type"], w["type"])
        wrong_rows += f"""
        <div class="wrong-item">
          <div class="wrong-head">
            <span class="tag">{type_label}</span>
            <span class="mono">{html.escape(w['id'])}</span>
            <span class="acc-badge" style="background:{bar_style(w['accuracy'])}22;color:{bar_style(w['accuracy'])}">
              正确率 {fmt_pct(w['accuracy'])}
            </span>
            <span class="dim">作答 {w['answer_count']} 次 / 对 {w['correct_count']}</span>
          </div>
          <div class="wrong-q">{html.escape(w['question'])}</div>
          <div class="wrong-ans"><b>正确答案:</b> {html.escape(str(w.get('answer','')))}</div>
          {('<div class="wrong-input"><b>你的作答:</b> ' + html.escape(str(w.get('last_input',''))[:150]) + '</div>') if w.get('last_input') else ''}
          <div class="wrong-exp"><b>解析:</b> {html.escape(w.get('explanation',''))}</div>
          {ai_block}
        </div>"""

    # 复习建议
    suggestions = []
    if overall is None:
        suggestions.append("还没有答题记录。运行每日学习脚本作答几次后，再来生成分析报告。")
    else:
        if overall >= 80:
            suggestions.append(f"整体正确率 {overall:.0f}% 表现优秀，建议保持节奏，集中攻克剩余薄弱知识点。")
        elif overall >= 60:
            suggestions.append(f"整体正确率 {overall:.0f}% 处于中游，建议优先复习正确率低于60%的知识点，并重做错题。")
        else:
            suggestions.append(f"整体正确率 {overall:.0f}% 偏低，建议放慢节奏，先系统复习知识点再刷题。")
        if wrong_count > 0:
            suggestions.append(f"有 {wrong_count} 道错题需要重做，系统已优先安排低正确率题目出现在每日学习中。")
        weak_kps = [k for k in kp_list if (k["accuracy"] or 0) < 60][:3]
        if weak_kps:
            names = "、".join(f"{k['id']}({k['topic']})" for k in weak_kps)
            suggestions.append(f"最薄弱的3个知识点: {names}，建议结合知识库详解重点复习。")
        suggestions.append("已作答题目不会频繁重复出现；正确率高的题目会降低出现频率，请放心持续刷题。")
    sug_html = "".join(f"<li>{html.escape(s)}</li>" for s in suggestions)

    today = datetime.date.today().isoformat()
    last_session = report.get("last_session") or "—"

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ESG学习情况分析报告</title>
<style>
:root {{
  --bg:#ffffff; --fg:#1a1a1a; --card:#f8f9fa; --border:#dee2e6;
  --accent:#0d6efd; --accent-light:#e7f1ff; --green:#198754; --red:#dc3545;
  --yellow:#ffc107; --dim:#6c757d;
}}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg); color:var(--fg); line-height:1.7;
  max-width:1000px; margin:0 auto; padding:28px 20px 60px;
}}
h1 {{ font-size:1.7em; border-bottom:3px solid var(--accent); padding-bottom:12px; }}
.sub {{ color:var(--dim); font-size:0.9em; margin-top:6px; }}
h2 {{ font-size:1.3em; margin:32px 0 12px; border-left:4px solid var(--accent); padding-left:12px; }}
.cards {{ display:flex; flex-wrap:wrap; gap:12px; margin:18px 0; }}
.card {{
  flex:1 1 150px; background:var(--card); border:1px solid var(--border);
  border-radius:10px; padding:14px 18px; text-align:center;
}}
.card .num {{ font-size:1.9em; font-weight:700; color:var(--accent); }}
.card .lbl {{ font-size:0.82em; color:var(--dim); }}
table {{ width:100%; border-collapse:collapse; margin:10px 0; font-size:0.9em; }}
th,td {{ border:1px solid var(--border); padding:7px 10px; text-align:center; }}
th {{ background:var(--accent-light); color:#0a4a9e; }}
tr:nth-child(even) {{ background:#fcfcfd; }}
.tl {{ text-align:left; }}
.mono {{ font-family:Consolas,"SF Mono",monospace; font-size:0.85em; color:#555; }}
.bar-cell {{ min-width:160px; }}
.bar {{ background:#e9ecef; border-radius:6px; height:12px; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:6px; }}
.wrong-item {{
  background:var(--card); border:1px solid var(--border); border-left:4px solid var(--red);
  border-radius:8px; padding:12px 16px; margin:10px 0;
}}
.wrong-head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:6px; }}
.tag {{ background:var(--accent-light); color:var(--accent); border-radius:10px; padding:1px 10px; font-size:0.78em; }}
.acc-badge {{ border-radius:10px; padding:1px 10px; font-size:0.8em; font-weight:600; }}
.dim {{ color:var(--dim); font-size:0.82em; }}
.wrong-q {{ font-weight:600; margin:4px 0; }}
.wrong-ans, .wrong-input, .wrong-exp {{ font-size:0.9em; margin:3px 0; }}
.wrong-exp {{ color:#333; }}
.ai-box {{ background:#fff3cd; border:1px solid #ffc107; border-radius:6px; padding:8px 12px; margin-top:6px; font-size:0.88em; }}
.sug {{ color:#8a6d00; margin-top:4px; }}
.sug-list {{ background:var(--accent-light); border-radius:8px; padding:14px 18px 14px 34px; margin-top:10px; }}
.sug-list li {{ margin:6px 0; }}
.note {{ color:var(--dim); font-size:0.85em; margin-top:8px; }}
</style>
</head>
<body>
<h1>ESG学习情况分析报告</h1>
<div class="sub">生成日期: {today} &nbsp;|&nbsp; 最近学习: {last_session} &nbsp;|&nbsp; 题库: 603题 / 74知识点</div>

<div class="cards">
  <div class="card"><div class="num">{total_answered}</div><div class="lbl">已作答题目</div></div>
  <div class="card"><div class="num">{total_answers}</div><div class="lbl">总作答次数</div></div>
  <div class="card"><div class="num">{fmt_pct(overall)}</div><div class="lbl">总正确率</div></div>
  <div class="card"><div class="num">{len(report['kp_stats'])}</div><div class="lbl">涉及知识点</div></div>
  <div class="card"><div class="num">{wrong_count}</div><div class="lbl">需复习错题</div></div>
</div>

<h2>各模块正确率</h2>
<table>
<tr><th class="tl">模块</th><th>涉及知识点</th><th>作答次数</th><th>正确率</th><th>分布</th></tr>
{mod_rows or '<tr><td colspan="5">暂无答题记录</td></tr>'}
</table>

<h2>知识点掌握情况 (薄弱优先)</h2>
<table>
<tr><th class="tl">知识点</th><th>作答次数</th><th>正确率</th><th>分布</th></tr>
{kp_rows or '<tr><td colspan="4">暂无答题记录</td></tr>'}
</table>

<h2>错题清单 ({wrong_count})</h2>
{wrong_rows or '<div class="note">暂无错题，继续保持！</div>'}

<h2>复习建议</h2>
<ul class="sug-list">{sug_html}</ul>

<div class="note">提示: 每日学习脚本会根据本报告自动优先安排薄弱题目。输入"分析数据表"可随时重新生成此报告。</div>
</body>
</html>"""

    with open(DEFAULT_OUT, "w", encoding="utf-8") as f:
        f.write(page)
    return DEFAULT_OUT


def main():
    parser = argparse.ArgumentParser(description="ESG学习情况分析报告生成器")
    parser.add_argument("--open", action="store_true", help="生成后用默认浏览器打开")
    parser.add_argument("--out", default=DEFAULT_OUT, help="输出HTML路径")
    args = parser.parse_args()

    progress, questions, kps = load()
    import progress_store
    report = progress_store.analyze_progress(progress, questions, kps)
    report["last_session"] = progress.get("last_session")

    path = build_html(report, kps)
    print(f"分析报告已生成: {path}")
    print(f"  总答题 {report['total_answers']} 次 | 正确率 {fmt_pct(report['overall_accuracy'])} | 错题 {len(report['wrong_questions'])} 道")

    if args.open:
        os.startfile(path)  # Windows
    return 0


if __name__ == "__main__":
    sys.exit(main())
