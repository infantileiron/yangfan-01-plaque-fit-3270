"""留出实测对账：两座打样台按纸样回传，乱序以修订号为准，缺测或冲突记待定。"""
from src.utils.csv_data import digest


def fold(records):
    """把回传记录折叠成 (纸样, 打样台) 台账，修订号大的为准。

    同一键位修订号相同而结论不同属于数据矛盾，整批拒绝；
    修订号相同结论相同是重复回传，去重不重复采信。
    """
    ledger = {}
    for record in records:
        key = (record["sample_id"], record["station"])
        current = ledger.get(key)
        if current is None or record["revision"] > current["revision"]:
            ledger[key] = record
        elif record["revision"] == current["revision"] and record["overflow"] != current["overflow"]:
            raise ValueError(
                f"纸样 {key[0]} 在{key[1]}的修订号 {record['revision']} 出现两种结论，请核实后重传。"
            )
    return ledger


def reconcile(sample_ids, ledger, stations):
    """按纸样逐一对账：两台结论一致才算对齐，缺测或两台冲突都记待定。"""
    resolved, pending = {}, []
    for sample_id in sample_ids:
        values = {station: ledger.get((sample_id, station)) for station in stations}
        missing = [station for station, record in values.items() if record is None]
        if missing:
            pending.append({
                "sample_id": sample_id, "reason": "缺测",
                "detail": "、".join(missing) + "未回传",
            })
        elif len({record["overflow"] for record in values.values()}) != 1:
            detail = "，".join(f"{station}测得{record['overflow']}" for station, record in values.items())
            pending.append({"sample_id": sample_id, "reason": "冲突", "detail": detail})
        else:
            resolved[sample_id] = next(iter(values.values()))["overflow"]
    return {"resolved": resolved, "pending": pending}


def snapshot(records, sample_ids, stations):
    """折叠当前台账并对账，产出单次预审从头到尾使用的同一批实测快照。"""
    ledger = fold(records)
    result = reconcile(sample_ids, ledger, stations)
    involved = set(sample_ids)
    canonical = [
        {"sample_id": sample_id, "station": station,
         "revision": record["revision"], "overflow": record["overflow"]}
        for (sample_id, station), record in sorted(ledger.items()) if sample_id in involved
    ]
    result["stations"] = list(stations)
    result["digest"] = digest(canonical)
    return result
