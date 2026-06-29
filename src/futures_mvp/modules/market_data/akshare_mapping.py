from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AkShareSymbolMapping:
    symbol: str
    akshare_symbol: str
    exchange: str
    display_name: str
    enabled: bool
    diagnostics: tuple[str, ...]


AKSHARE_SYMBOL_MAPPINGS: dict[str, AkShareSymbolMapping] = {
    "ao": AkShareSymbolMapping(
        symbol="ao",
        akshare_symbol="AO0",
        exchange="SHFE",
        display_name="氧化铝",
        enabled=True,
        diagnostics=("显式映射", "开发验证历史行情源"),
    ),
    "rb": AkShareSymbolMapping(
        symbol="rb",
        akshare_symbol="RB0",
        exchange="SHFE",
        display_name="螺纹钢",
        enabled=True,
        diagnostics=("显式映射", "开发验证历史行情源"),
    ),
    "ag": AkShareSymbolMapping(
        symbol="ag",
        akshare_symbol="AG0",
        exchange="SHFE",
        display_name="白银",
        enabled=True,
        diagnostics=("显式映射", "开发验证历史行情源"),
    ),
    "cu": AkShareSymbolMapping(
        symbol="cu",
        akshare_symbol="CU0",
        exchange="SHFE",
        display_name="铜",
        enabled=True,
        diagnostics=("显式映射", "开发验证历史行情源"),
    ),
}


def get_akshare_mapping(symbol: str) -> AkShareSymbolMapping | None:
    return AKSHARE_SYMBOL_MAPPINGS.get(symbol.strip().lower())


def enabled_akshare_symbols() -> tuple[str, ...]:
    return tuple(
        sorted(
            symbol
            for symbol, mapping in AKSHARE_SYMBOL_MAPPINGS.items()
            if mapping.enabled
        )
    )


def akshare_mapping_rows() -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for mapping in AKSHARE_SYMBOL_MAPPINGS.values():
        rows.append((f"{mapping.symbol}:品种", mapping.display_name))
        rows.append((f"{mapping.symbol}:AkShare 符号", mapping.akshare_symbol))
        rows.append((f"{mapping.symbol}:交易所", mapping.exchange))
        rows.append((f"{mapping.symbol}:是否启用", "是" if mapping.enabled else "否"))
        rows.append((f"{mapping.symbol}:映射诊断", "；".join(mapping.diagnostics)))
    return tuple(rows)
