"""Visible catalog authorities for cutting; no geometry or packing formulas."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.db import connection

from dekopen_engine.cutting import (
    AmbiguousCuttingProfile,
    AmbiguousStockAuthority,
    CutMaterial,
    CuttingProfile,
    MissingCuttingProfile,
    MissingStockAuthority,
    StockRule,
)
from dekopen_engine.models import EngineResult
from engine_api.repository import SystemParamsRepository, _decimal


@dataclass(frozen=True)
class CuttingAuthorities:
    stocks: list[StockRule]
    reinforcement_skus: dict[str, str]
    reinforcement_ix: dict[str, Decimal | None]


def _positive_stock_length(value) -> Decimal:
    # NULL is UNKNOWN — the catalog never stated a commercial length, so the
    # optimizer has no bar to nest against. Refuse rather than invent one.
    if value is None:
        raise MissingStockAuthority(
            "Stock length unknown — declare commercial_length_mm on the article"
        )
    length = _decimal(value)
    if length <= Decimal("0"):
        raise MissingStockAuthority("Stock length must be positive")
    return length


def effective_scope(
    rows: list[tuple[object, ...]], org_id: UUID, scope_index: int
) -> list[tuple[object, ...]]:
    tenant = [row for row in rows if str(row[scope_index]) == str(org_id)]
    return tenant if tenant else [row for row in rows if row[scope_index] is None]


def steel_color_map(stocks: list[StockRule]) -> dict[str, str]:
    """D05: workshop sku → declared stock color for the steel rules, so
    cut pieces stamp the reinforcement's own finish, not the bar's."""
    return {
        stock.workshop_sku: stock.color
        for stock in stocks
        if stock.material is CutMaterial.STEEL
    }


class CuttingRepository:
    def cutting_profile(self, org_id: UUID, code: str | None = None) -> CuttingProfile:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id, code, kerf_mm, head_trim_mm, tail_trim_mm, org_id
                   FROM public.cutting_profiles
                   WHERE is_active AND (org_id IS NULL OR org_id=%s)
                     AND ((%s IS NULL AND is_default) OR code=%s)
                   ORDER BY id""",
                [org_id, code, code],
            )
            rows = cursor.fetchall()
        if code is None:
            rows = effective_scope(rows, org_id, 5)
        if not rows:
            raise MissingCuttingProfile
        if len(rows) != 1:
            raise AmbiguousCuttingProfile
        row = rows[0]
        return CuttingProfile(
            id=str(row[0]),
            code=str(row[1]),
            kerf_mm=_decimal(row[2]),
            head_trim_mm=_decimal(row[3]),
            tail_trim_mm=_decimal(row[4]),
        )

    def profile_stock(self, system_id: UUID, org_id: UUID, sku: str, color: str) -> StockRule:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id, commercial_length_mm, material::text
                   FROM public.profile_articles WHERE system_id=%s AND sku=%s
                     AND (org_id IS NULL OR org_id=%s) ORDER BY id""",
                [system_id, sku, org_id],
            )
            articles = cursor.fetchall()
            if not articles:
                raise MissingStockAuthority
            if len(articles) != 1:
                raise AmbiguousStockAuthority
            article = articles[0]
            # D05: the stocked bar is finish-keyed — the mapping's declared
            # stock_color must equal the requested key (plain code or the
            # bicolor "EXT/INT" key) rather than silently serving the base
            # white bar for a foliado purchase order. A NULL stock_color is
            # a legacy color-agnostic bar that serves any finish; two viable
            # bars for one finish stay ambiguous — never silently preferred.
            cursor.execute(
                """SELECT id, commercial_sku, manufacturer_name, supplier_name,
                          purchase_unit, org_id
                   FROM public.profile_purchase_mappings
                   WHERE profile_article_id=%s AND is_active
                     AND (stock_color IS NULL OR stock_color=%s)
                     AND (org_id IS NULL OR org_id=%s) ORDER BY id""",
                [article[0], color, org_id],
            )
            rows = effective_scope(cursor.fetchall(), org_id, 5)
        if not rows:
            raise MissingStockAuthority
        if len(rows) != 1:
            raise AmbiguousStockAuthority
        row = rows[0]
        if row[4] != "BAR":
            raise MissingStockAuthority("Stock is not supplied as bars")
        return StockRule(
            stock_authority_id=str(row[0]),
            workshop_sku=sku,
            commercial_sku=str(row[1]),
            manufacturer_name=str(row[2]),
            supplier_name=None if row[3] is None else str(row[3]),
            purchase_unit="BAR",
            material=CutMaterial(str(article[2])),
            color=color,
            stock_length_mm=_positive_stock_length(article[1]),
        )

    def reinforcement_stock(
        self,
        system_id: UUID,
        org_id: UUID,
        parent_sku: str,
        requested_sku: str | None = None,
    ) -> tuple[StockRule, Decimal | None]:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id FROM public.profile_articles WHERE system_id=%s AND sku=%s
                     AND (org_id IS NULL OR org_id=%s) ORDER BY id""",
                [system_id, parent_sku, org_id],
            )
            parents = cursor.fetchall()
            if not parents:
                raise MissingStockAuthority
            if len(parents) != 1:
                raise AmbiguousStockAuthority
            cursor.execute(
                """SELECT id, sku, commercial_sku, manufacturer_name, supplier_name,
                          stock_length_mm, purchase_unit, ix_cm4, org_id, stock_color
                   FROM public.reinforcement_articles
                   WHERE system_id=%s AND parent_profile_article_id=%s AND is_active
                     AND (org_id IS NULL OR org_id=%s)
                     AND ((%s IS NULL AND is_default) OR sku=%s) ORDER BY id""",
                [system_id, parents[0][0], org_id, requested_sku, requested_sku],
            )
            rows = effective_scope(cursor.fetchall(), org_id, 8)
        if not rows:
            raise MissingStockAuthority
        if len(rows) != 1:
            raise AmbiguousStockAuthority
        row = rows[0]
        if row[6] != "BAR":
            raise MissingStockAuthority
        # D05: steel is colorless relative to the bar finish — the rule
        # carries the steel's own declared stock_color, never the profile's
        # finish key the caller resolved.
        return StockRule(
            stock_authority_id=str(row[0]),
            workshop_sku=str(row[1]),
            commercial_sku=str(row[2]),
            manufacturer_name="" if row[3] is None else str(row[3]),
            supplier_name=None if row[4] is None else str(row[4]),
            purchase_unit="BAR",
            material=CutMaterial.STEEL,
            color=str(row[9]) if row[9] else "WHITE",
            stock_length_mm=_positive_stock_length(row[5]),
        ), None if row[7] is None else _decimal(row[7])

    def for_result(
        self,
        result: EngineResult,
        system_id: UUID,
        org_id: UUID,
        color: str,
    ) -> CuttingAuthorities:
        # Also verifies that the requested system is visible and active through the original loader.
        SystemParamsRepository().load_visible(system_id, org_id)
        stocks: dict[str, StockRule] = {}
        defaults: dict[str, str] = {}
        inertias: dict[str, Decimal | None] = {}
        for sku in sorted({cut.sku for cut in result.profile_cuts}):
            stock = self.profile_stock(system_id, org_id, sku, color)
            stocks[stock.stock_authority_id] = stock
        identities = {
            (cut.parent_profile_sku, cut.reinforcement_sku) for cut in result.reinforcements
        }
        for parent, requested in sorted(identities, key=lambda x: (x[0], x[1] or "")):
            stock, ix = self.reinforcement_stock(system_id, org_id, parent, requested)
            stocks[stock.stock_authority_id] = stock
            if requested is None:
                defaults[parent] = stock.workshop_sku
            inertias[parent] = ix
        return CuttingAuthorities([stocks[key] for key in sorted(stocks)], defaults, inertias)
