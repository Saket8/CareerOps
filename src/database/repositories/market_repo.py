"""Market repository for tracking skill frequencies and historical trends."""

from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.models import MarketSignalModel


class MarketSignalRepository:
    def __init__(self, session: Session):
        self.session = session

    def record_signal(self, signal_date: str, item_name: str, category: str, frequency: int = 1, trend: str = "STABLE") -> MarketSignalModel:
        existing = (
            self.session.query(MarketSignalModel)
            .filter(
                MarketSignalModel.signal_date == signal_date,
                MarketSignalModel.item_name == item_name,
                MarketSignalModel.category == category,
            )
            .first()
        )
        if existing:
            existing.frequency += frequency
            existing.trend = trend
            self.session.flush()
            return existing

        signal = MarketSignalModel(
            signal_date=signal_date,
            item_name=item_name,
            category=category,
            frequency=frequency,
            trend=trend,
        )
        self.session.add(signal)
        self.session.flush()
        return signal

    def get_signals_by_date(self, signal_date: str) -> List[MarketSignalModel]:
        return self.session.query(MarketSignalModel).filter(MarketSignalModel.signal_date == signal_date).all()

    def get_top_items_by_category(self, category: str, limit: int = 20) -> List[Dict[str, Any]]:
        results = (
            self.session.query(
                MarketSignalModel.item_name,
                func.sum(MarketSignalModel.frequency).label("total_freq"),
            )
            .filter(MarketSignalModel.category == category)
            .group_by(MarketSignalModel.item_name)
            .order_by(func.sum(MarketSignalModel.frequency).desc())
            .limit(limit)
            .all()
        )
        return [{"name": r[0], "count": int(r[1])} for r in results]
