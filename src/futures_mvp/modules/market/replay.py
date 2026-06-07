from collections.abc import Sequence
from dataclasses import dataclass

from futures_mvp.domain.enums import MarketDataResultStatus
from futures_mvp.domain.models import Bar, Tick
from futures_mvp.modules.market.canonical import canonical_bar_payload, canonical_tick_payload
from futures_mvp.modules.market.quality import DataQualityPolicy
from futures_mvp.modules.market.service import MarketDataIngestResult, MarketDataService

MarketFact = Tick | Bar


@dataclass(frozen=True)
class MarketReplayResult:
    results: tuple[MarketDataIngestResult, ...]

    @property
    def has_error(self) -> bool:
        return any(result.result.status is MarketDataResultStatus.ERROR for result in self.results)


def replay_market_facts(
    service: MarketDataService,
    facts: Sequence[MarketFact],
    *,
    policy: DataQualityPolicy | None = None,
) -> MarketReplayResult:
    results: list[MarketDataIngestResult] = []
    for fact in sorted(facts, key=_market_fact_sort_key):
        if isinstance(fact, Tick):
            results.append(service.ingest_tick(fact, policy=policy))
        else:
            results.append(service.ingest_bar(fact, policy=policy))
    return MarketReplayResult(results=tuple(results))


def _market_fact_sort_key(fact: MarketFact) -> tuple[object, ...]:
    ts = fact.ts if isinstance(fact, Tick) else fact.bar_ts
    fact_type = "TICK" if isinstance(fact, Tick) else "BAR"
    timeframe = "" if isinstance(fact, Tick) else fact.timeframe.value
    return (
        ts,
        fact.exchange,
        fact.instrument_id,
        fact.source,
        fact_type,
        timeframe,
        fact.symbol,
        fact.trade_instrument_id,
        _canonical_fingerprint(fact),
    )


def _canonical_fingerprint(fact: MarketFact) -> str:
    payload = (
        canonical_tick_payload(fact)
        if isinstance(fact, Tick)
        else canonical_bar_payload(fact)
    )
    return repr(tuple(_stable_value(value) for value in payload))


def _stable_value(value: object) -> object:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
