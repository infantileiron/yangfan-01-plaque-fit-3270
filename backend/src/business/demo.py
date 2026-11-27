from random import Random

from .profile import PROFILE

TEMPLATES = [f"LY-T{index:02d}" for index in range(1, 14)]
LANGUAGES = ["中文/英文", "中文/法文", "中文/德文", "中文/日文"]


def demo_batch():
    """训练底稿与待校参数随数据版本导入；留出实测由两座打样台分别回传。"""
    rng = Random(53125)
    rows, measurements = [], []
    for index in range(240):
        template_index = rng.choices(range(13), [14, 14, 12, 11, 10, 9, 8, 6, 5, 4, 3, 2, 2])[0]
        lang_index = rng.randrange(4)
        width, lines = rng.choice([62, 75, 88, 101]), rng.choice([2, 3, 4])
        ratio = round(rng.uniform(0.61, 1.31), 3)
        limit = 1.03 + (template_index % 4 - 1.5) * 0.06 + [0.025, 0.0, -0.07, 0.075][lang_index]
        label = "是" if ratio + rng.gauss(0, 0.045) > limit else "否"
        sample_id = f"LY-H{index + 1:03}"
        split = "训练" if index < 192 else "留出"
        rows.append(sample(sample_id, split, TEMPLATES[template_index], LANGUAGES[lang_index],
                           width, lines, ratio, label if split == "训练" else None))
        if split == "留出":
            measurements.extend(station_reports(sample_id, label))
    pending = [
        (0, 2, 75, 3, 1.32), (1, 0, 88, 4, 0.65), (4, 2, 62, 3, 1.18),
        (6, 0, 101, 2, 1.07), (2, 3, 75, 4, 0.99), (2, 1, 62, 3, 0.67),
        (8, 3, 88, 3, 1.10), (0, 4, 75, 3, 0.76),
    ]
    for index, (template, lang, width, lines, ratio) in enumerate(pending, start=1):
        language = LANGUAGES[lang] if lang < len(LANGUAGES) else "中文/芬兰文"
        rows.append(sample(f"LY-P{index:02}", "待校", TEMPLATES[template], language, width, lines, ratio, None))
    return rows, measurements


def station_reports(sample_id, label):
    first, second = PROFILE["stations"]
    other = "否" if label == "是" else "是"
    if sample_id == "LY-H237":  # 1 号台先错后改，乱序到达以修订号 2 为准
        return [report(sample_id, first, 2, label), report(sample_id, second, 1, label),
                report(sample_id, first, 1, other)]
    if sample_id == "LY-H210":  # 2 号台尚未回传，缺测待定
        return [report(sample_id, first, 1, label)]
    if sample_id == "LY-H223":  # 2 号台测反，冲突待定
        return [report(sample_id, first, 1, label), report(sample_id, second, 1, other)]
    if sample_id == "LY-H204":  # 1 号台测反，冲突待定
        return [report(sample_id, first, 1, other), report(sample_id, second, 1, label)]
    return [report(sample_id, first, 1, label), report(sample_id, second, 1, label)]


def report(sample_id, station, revision, overflow):
    return {"sample_id": sample_id, "station": station, "revision": revision, "overflow": overflow}


def sample(sample_id, split, template, language, width, lines, ratio, label):
    return {
        "sample_id": sample_id, "split": split, "template": template, "lang_pair": language,
        "width_mm": width, "lines": lines, "ink_mm": round(width * lines * ratio, 2), "overflow": label,
    }
