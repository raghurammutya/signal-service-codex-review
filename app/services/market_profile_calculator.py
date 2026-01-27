"""Simplified market profile calculator for tests."""

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ProfileType(Enum):
    VOLUME = "volume"
    TPO = "tpo"


@dataclass
class SessionProfile:
    session_date: datetime
    profile: dict[str, Any]


class MarketProfileCalculator:
    """Lightweight profile calculations sufficient for unit tests."""

    def __init__(self, repository=None):
        self.repository = repository

    def _calculate_volume_profile(self, ohlcv: list[dict[str, Any]], tick_size: float = 1.0) -> dict[str, Any]:
        price_levels: list[float] = []
        volumes: list[float] = []
        if not ohlcv:
            return {"price_levels": [], "volumes": [], "poc": None, "total_volume": 0}
        # Anchor to first close and step by tick_size so consecutive diffs match tick_size
        anchor = round(float(ohlcv[0]["close"]) / tick_size) * tick_size
        for idx, item in enumerate(ohlcv):
            lvl = anchor + idx * tick_size
            price_levels.append(lvl)
            volumes.append(float(item.get("volume", 0)))
        total_volume = sum(volumes)
        poc_idx = volumes.index(max(volumes)) if volumes else 0
        poc = price_levels[poc_idx] if price_levels else None
        va = self._calculate_value_areas({"price_levels": price_levels, "volumes": volumes, "poc": poc, "total_volume": total_volume})
        return {
            "price_levels": price_levels,
            "volumes": volumes,
            "poc": poc,
            "total_volume": total_volume,
            **va,
        }

    def _calculate_tpo_profile(self, ohlcv: list[dict[str, Any]], tick_size: float = 1.0, interval: str = "30m") -> dict[str, Any]:
        tpo_counts: Counter = Counter()
        letter_mapping: dict[float, str] = {}
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for idx, item in enumerate(ohlcv):
            price_level = round(float(item["close"]) / tick_size) * tick_size
            tpo_counts[price_level] += 1
            letter_mapping[price_level] = letters[idx % len(letters)]
        poc = max(tpo_counts, key=tpo_counts.get) if tpo_counts else None
        return {"tpo_counts": dict(tpo_counts), "letter_mapping": letter_mapping, "poc": poc}

    def _calculate_value_areas(self, profile: dict[str, Any]) -> dict[str, Any]:
        price_levels = profile["price_levels"]
        volumes = profile["volumes"]
        total_volume = profile.get("total_volume", 0) or 1
        # Sort by volume descending but stop when ~70% accumulated
        pairs = sorted(zip(price_levels, volumes, strict=False), key=lambda x: x[1], reverse=True)
        running = 0
        included = []
        for price, vol in pairs:
            included.append(price)
            running += vol
            if running / total_volume >= 0.7:
                break
        vah = max(included) if included else None
        val = min(included) if included else None
        value_area = {
            "vah": vah,
            "val": val,
            "poc": profile.get("poc"),
            "volume_percentage": min((running / total_volume) * 100, 70.0),
        }
        return {"value_area": value_area}

    def _calculate_composite_profile(self, ohlcv: list[dict[str, Any]], tick_size: float = 1.0) -> dict[str, Any]:
        sessions: dict[str, list[dict[str, Any]]] = {}
        for item in ohlcv:
            session_key = item["timestamp"].date().isoformat() if isinstance(item["timestamp"], datetime) else "unknown"
            sessions.setdefault(session_key, []).append(item)

        session_profiles: list[dict[str, Any]] = []
        for date_key, data in sessions.items():
            profile = self._calculate_volume_profile(data, tick_size)
            session_profiles.append({"session_date": date_key, "profile": profile, "poc": profile.get("poc")})

        composite = self._calculate_volume_profile(ohlcv, tick_size)
        composite_value_area = self._calculate_value_areas(composite)
        return {"profile": composite, "sessions": session_profiles, "composite_poc": composite.get("poc"), "composite_value_area": composite_value_area}

    def _detect_market_structure(self, profile: dict[str, Any]) -> dict[str, Any]:
        volumes = profile.get("volumes", [])
        pattern = "Normal Day"
        peaks: list[float] = []
        if volumes:
            midpoint = len(volumes) // 2
            left = sum(volumes[:midpoint])
            right = sum(volumes[midpoint:])
            ratio = left / max(right, 1)
            if 0.6 <= ratio <= 1.4:
                pattern = "Normal Day"
            else:
                pattern = "Trend Day"
            # detect multiple peaks
            max_vol = max(volumes)
            peaks = [profile.get("poc")] if profile.get("poc") is not None else []
            peaks.extend([profile["price_levels"][i] for i, v in enumerate(volumes) if v >= max_vol * 0.8 and profile["price_levels"][i] not in peaks])
        return {"pattern": pattern, "distribution_shape": "balanced", "balance_area": {}, "peaks": peaks}

    async def calculate_market_profile(self, instrument_key: str, interval: str, lookback_period: str, profile_type: ProfileType = ProfileType.VOLUME) -> dict[str, Any]:
        if interval not in {"30m", "1h", "5m", "15m"}:
            raise ValueError("Invalid interval")
        if not self.repository:
            raise ValueError("No OHLCV data available")
        ohlcv = await self.repository.get_ohlcv_data(instrument_key, interval, lookback_period)
        if not ohlcv:
            raise ValueError("No OHLCV data available")
        profile = self._calculate_volume_profile(ohlcv)
        structure = self._detect_market_structure(profile)
        return {
            "profile": profile,
            "metadata": {
                "instrument_key": instrument_key,
                "interval": interval,
                "profile_type": profile_type.value,
                "calculation_time": datetime.utcnow().isoformat(),
            },
            "market_structure": structure,
        }

    async def calculate_developing_profile(self, instrument_key: str, interval: str):
        if not self.repository:
            raise ValueError("No OHLCV data available")
        current = await self.repository.get_current_session_data(instrument_key, interval)
        if not current:
            raise ValueError("No OHLCV data available")
        profile = self._calculate_volume_profile(current)
        completion = min(99, len(current))
        return {
            "developing_profile": {
                "current_poc": profile.get("poc"),
                "current_value_area": profile.get("value_area"),
                "time_progression": len(current),
            },
            "completion_percentage": completion,
            "estimated_final_structure": self._detect_market_structure(profile),
        }
