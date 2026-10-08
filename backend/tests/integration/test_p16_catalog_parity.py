"""P16 — readiness parity: the system page must show PASS/WARN/BLOCK
computed by the SAME function that gates quote emission and production
release (``catalogs.readiness.catalog_readiness``). A workspace that
recomputed or decorated its own verdict would silently disagree with the
gates — this test pins the identity for every fixture shape.
"""

import pytest

from backend.tests.integration.test_shot09_documentary import (
    as_user,
    documentary_tenant as documentary_tenant,
)
from backend.tests.integration.catalog_fixture import copy_fixed_catalog
from catalogs.readiness import catalog_readiness
from catalogs import service as catalog_service
from documents.repository import one

pytestmark = pytest.mark.rls_integration


def _workspace_readiness(org, system_id, owner):
    with as_user(owner):
        workspace = catalog_service.system_workspace(org, system_id)
    return workspace["system"]["readiness"]


def test_workspace_readiness_parity_demo60(documentary_tenant):
    """DEMO_60 (complete fixture): the workspace's embedded readiness IS the
    gate's readiness — same levels, same blockers, same quote_ready."""
    org, _, users, _ = documentary_tenant
    system_id = one(
        "SELECT id FROM public.profile_systems WHERE code='DEMO_60'"
    )["id"]
    with as_user(users["OWNER"]):
        gate = catalog_readiness(system_id, org)
    page = _workspace_readiness(org, system_id, users["OWNER"])
    assert page == gate
    assert page["quote_ready"] == gate["quote_ready"]
    assert page["reasons"] == gate["reasons"]


def test_workspace_readiness_parity_incomplete(documentary_tenant):
    """Incomplete fixture (org clone missing fabrication authorities): the
    ladder and blockers — including the P16 deep-link targets — are
    identical between the page and the gate."""
    org, _, users, _ = documentary_tenant
    system_id = copy_fixed_catalog(org)
    with as_user(users["OWNER"]):
        gate = catalog_readiness(system_id, org)
    page = _workspace_readiness(org, system_id, users["OWNER"])
    assert page == gate
    assert not page["quote_ready"]
    assert page["reasons"] == gate["reasons"]
    # Every blocker a gate blocks on carries a resolvable deep link.
    for level in page["levels"]:
        for blocker in level["blockers"]:
            assert blocker["targets"], blocker["code"]
            target = blocker["targets"][0]
            assert target["tab"]
            assert target["label"]
