import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .encoding import TargetStats
from .selection import compare


def occupation(row):
    if not float(row["lines"]).is_integer() or row["lines"] <= 0 or row["width_mm"] <= 0:
        raise ValueError("预留行数必须为正整数，单行宽度必须大于零。")
    return row["ink_mm"] / (row["width_mm"] * row["lines"])


def features(rows, stats=None, labels=None):
    return [
        [occupation(row), row["lines"]] + (stats.encode(row, labels[index] if labels is not None else None) if stats else [])
        for index, row in enumerate(rows)
    ]


def checked_labels(values, group):
    if any(value not in {"是", "否"} for value in values):
        raise ValueError(f"{group}纸样必须标明是否溢出。")
    labels = [int(value == "是") for value in values]
    if len(set(labels)) != 2:
        raise ValueError(f"{group}纸样须同时包含溢出和未溢出实例。")
    return labels


def label_set(rows, group):
    return checked_labels([row["overflow"] for row in rows], group)


def fit(training, labels, stats=None):
    model = make_pipeline(StandardScaler(), LogisticRegression(C=1.8, max_iter=500, random_state=77))
    model.fit(features(training, stats, labels), labels)
    return model


def squared_errors(model, rows, labels, stats=None):
    probabilities = model.predict_proba(features(rows, stats))[:, 1]
    return probabilities, (probabilities - np.asarray(labels)) ** 2


def analyze(rows, parameter, evidence):
    training = [row for row in rows if row["split"] == "训练"]
    holdout = [row for row in rows if row["split"] == "留出"]
    candidates = [row for row in rows if row["split"] == "待校"]
    resolved = evidence["resolved"]
    pending_notes = {item["sample_id"]: item for item in evidence["pending"]}
    aligned = [row for row in holdout if row["sample_id"] in resolved]
    pending = [row for row in holdout if row["sample_id"] not in resolved]
    if len(training) < 30 or len(aligned) < 12 or not candidates:
        raise ValueError(
            f"至少需要 30 个训练、12 个已对齐留出及 1 个待校纸样；"
            f"当前已对齐 {len(aligned)} 个、待定 {len(pending)} 个。请等待打样台回传后重试。"
        )
    if any(row["overflow"] is not None for row in candidates):
        raise ValueError("待校纸样的实测溢出列必须留空。")
    train_labels = label_set(training, "训练")
    holdout_labels = checked_labels([resolved[row["sample_id"]] for row in aligned], "留出")
    stats = TargetStats(training, train_labels)
    base, encoded = fit(training, train_labels), fit(training, train_labels, stats)
    _, base_errors = squared_errors(base, aligned, holdout_labels)
    _, encoded_errors = squared_errors(encoded, aligned, holdout_labels, stats)
    base_brier, encoded_brier = float(base_errors.mean()), float(encoded_errors.mean())
    pending_deltas = []
    if pending:
        base_prob = base.predict_proba(features(pending))[:, 1]
        encoded_prob = encoded.predict_proba(features(pending, stats))[:, 1]
        pending_deltas = [
            (float(encoded_prob[i] ** 2 - base_prob[i] ** 2),
             float((1 - encoded_prob[i]) ** 2 - (1 - base_prob[i]) ** 2))
            for i in range(len(pending))
        ]
    use_encoded, firm = compare(float((encoded_errors - base_errors).sum()), pending_deltas)
    version = "目标编码" if use_encoded else "几何基准"
    model = encoded if use_encoded else base
    probabilities = model.predict_proba(features(candidates, stats if use_encoded else None))[:, 1]
    outputs = []
    for row, probability in zip(candidates, probabilities):
        unseen = stats.unseen(row)
        high = probability >= parameter
        decision = "人工重排" if high else "补纸样" if unseen else "常规纸样"
        basis = "达到重排阈值" if high else "低于重排阈值"
        if unseen:
            basis += "；缺少历史" + "及".join(unseen)
            basis += "，回退训练先验" if use_encoded else "，须补纸样"
        if not firm:
            basis += f"；暂用{version}版（{len(pending)} 条留出实测待定，复测到齐后重判）"
        outputs.append({
            "sample_id": row["sample_id"], "template": row["template"] + " / " + row["lang_pair"],
            "fill": round(occupation(row) * 100, 1), "probability": round(float(probability) * 100, 2),
            "decision": decision, "evidence": basis,
        })
    order = {"人工重排": 0, "补纸样": 1, "常规纸样": 2}
    outputs.sort(key=lambda item: (order[item["decision"]], -item["probability"], item["sample_id"]))
    urgent = sum(item["decision"] == "人工重排" for item in outputs)
    summary = f"{len(outputs)} 个待校纸样，{urgent} 个进入人工重排"
    if not firm:
        summary += "（暂用结果，待复测重判）"
    reasons = [pending_notes.get(row["sample_id"], {}).get("reason", "缺测") for row in pending]
    missing = reasons.count("缺测")
    notes = [
        "Brier 越小代表本次留出的概率误差越低。两版模型在同一批已对齐实测上比较，留出仅用于择优。",
        "占位率是排版几何估计。换行、连字与字体替换仍须在 1:1 实际纸样上复核。",
        f"留出实测按纸样与打样台对账，乱序回传以修订号为准；本次预审全程使用同一批实测快照 {evidence['digest'][:12]}。",
    ]
    if pending:
        listed = "、".join(f"{row['sample_id']}（{reason}）" for row, reason in zip(pending, reasons))
        notes.append(
            f"留出实测未齐：{len(pending)} 条待定（缺测 {missing} 条、两台冲突 {len(pending) - missing} 条），"
            f"复测到齐后重判择优。待定纸样：{listed}。"
        )
        notes.append(
            "待定纸样无论最终如何判定，均不影响本次择优结论。" if firm
            else f"待定纸样的最终判定可能翻转择优结论，当前暂用{version}版出具结果。"
        )
    return {
        "summary": summary,
        "metrics": [
            {"label": "几何基准 Brier", "value": round(base_brier, 4)},
            {"label": "目标编码 Brier", "value": round(encoded_brier, 4)},
            {"label": "本批择优", "value": version},
            {"label": "择优口径", "value": "正式" if firm else "暂用"},
            {"label": "已对齐留出", "value": len(aligned)},
            {"label": "待定纸样", "value": len(pending)},
            {"label": "实测快照", "value": evidence["digest"][:12]},
        ],
        "rows": outputs,
        "notes": notes,
    }
