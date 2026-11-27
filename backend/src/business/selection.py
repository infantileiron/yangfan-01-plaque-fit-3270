"""两版模型在同一批已对齐实测上比较概率误差，待定纸样按最不利情形兜底。"""


def compare(delta_resolved, pending_deltas):
    """判定是否换用挑战版模型。

    delta_resolved：已对齐纸样上「挑战版误差 − 现任版误差」的合计。
    pending_deltas：每条待定纸样的 (判否时的差值, 判是时的差值)。
    待定纸样无论怎么判挑战版都领先才换版；现任版铁定领先则结论正式；
    两者都不是说明待定判定可能翻转结论，暂用现任版，待复测到齐后重判。
    返回 (是否换版, 结论是否正式)。
    """
    if not pending_deltas:
        return delta_resolved < 0, True
    lower = delta_resolved + sum(min(options) for options in pending_deltas)
    upper = delta_resolved + sum(max(options) for options in pending_deltas)
    if upper < 0:
        return True, True
    if lower > 0:
        return False, True
    return False, False
