from datetime import datetime

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, new_id, utcnow


class Measurement(Base):
    """打样台回传的留出实测台账，按 (纸样, 打样台) 对折，修订号大的为准。"""
    __tablename__ = "measurements"
    __table_args__ = (UniqueConstraint("sample_id", "station"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sample_id: Mapped[str] = mapped_column(String(120), index=True)
    station: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int]
    overflow: Mapped[str] = mapped_column(String(2))
    actor: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
