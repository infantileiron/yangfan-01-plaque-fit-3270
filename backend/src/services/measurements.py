from fastapi import HTTPException
from sqlalchemy import select, tuple_

from src.business import reconcile
from src.business.profile import PROFILE
from src.config.settings import Session
from src.models.measurement import Measurement
from src.schemas.resources import measurement_view
from src.services import datasets
from src.services.audit import record
from src.utils.csv_data import digest, parse_csv


def parse_batch(contents):
    try:
        return parse_csv(contents, PROFILE["measurement_columns"], unique=("sample_id", "station", "revision"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def apply_records(db, records, actor):
    """按 (纸样, 打样台) 台账采信回传：修订号大的覆盖，小的记过期，相同不重复采信。"""
    try:
        folded = reconcile.fold(records)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    existing = {}
    if folded:
        rows = db.scalars(
            select(Measurement)
            .where(tuple_(Measurement.sample_id, Measurement.station).in_(list(folded)))
            .with_for_update()
        ).all()
        existing = {(row.sample_id, row.station): row for row in rows}
    counts = {"applied": 0, "unchanged": 0, "stale": 0}
    conflicts = []
    for (sample_id, station), item in folded.items():
        current = existing.get((sample_id, station))
        if current is None:
            db.add(Measurement(sample_id=sample_id, station=station, actor=actor,
                               revision=item["revision"], overflow=item["overflow"]))
            counts["applied"] += 1
        elif item["revision"] > current.revision:
            current.revision = item["revision"]
            current.overflow = item["overflow"]
            current.actor = actor
            counts["applied"] += 1
        elif item["revision"] == current.revision:
            if item["overflow"] != current.overflow:
                conflicts.append(f"{sample_id} 在{station}的修订号 {item['revision']}")
            else:
                counts["unchanged"] += 1
        else:
            counts["stale"] += 1
    if conflicts:
        raise HTTPException(422, "同修订号结论与台账不符：" + "；".join(conflicts) + "。请核实后重传。")
    return counts


def ingest(contents, actor):
    records = parse_batch(contents)
    with Session.begin() as db:
        counts = apply_records(db, records, actor)
        subject = digest([item for key, item in sorted(reconcile.fold(records).items())])[:16]
        record(db, actor, "measurements_ingested", subject)
        return {"received": len(records), **counts}


def snapshot_for(db, sample_ids):
    """按当前台账为计算单冻结实测快照，单次预审从头到尾使用同一批实测。"""
    rows = db.scalars(select(Measurement).where(Measurement.sample_id.in_(sample_ids))).all() if sample_ids else []
    records = [
        {"sample_id": row.sample_id, "station": row.station, "revision": row.revision, "overflow": row.overflow}
        for row in rows
    ]
    return reconcile.snapshot(records, sample_ids, PROFILE["stations"])


def list_ledger():
    with Session() as db:
        rows = db.scalars(select(Measurement).order_by(Measurement.sample_id, Measurement.station)).all()
        return {"stations": PROFILE["stations"], "rows": [measurement_view(row) for row in rows]}


def reconciliation(dataset_id):
    with Session() as db:
        dataset = datasets.require(db, dataset_id)
        sample_ids = [row["sample_id"] for row in dataset.rows if row["split"] == "留出"]
        current = snapshot_for(db, sample_ids)
        rows = db.scalars(
            select(Measurement).where(Measurement.sample_id.in_(sample_ids))
            .order_by(Measurement.sample_id, Measurement.station)
        ).all() if sample_ids else []
        return {
            "stations": current["stations"], "holdout": len(sample_ids),
            "resolved": len(current["resolved"]), "pending": current["pending"],
            "digest": current["digest"], "ledger": [measurement_view(row) for row in rows],
        }
