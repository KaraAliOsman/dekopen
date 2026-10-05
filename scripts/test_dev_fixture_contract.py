from pathlib import Path


SOURCE = Path(__file__).with_name("dev_fixture.py").read_text(encoding="utf-8")


def test_dev_fixture_declares_two_realistic_organizations() -> None:
    assert 'ORG_NAME = "Ventanas del Sur SpA"' in SOURCE
    assert 'ORG_B_NAME = "Cristales del Norte Ltda."' in SOURCE
    # The OWNER account belongs to both orgs so the org selector is real.
    assert '"membership-owner-b"' in SOURCE
    assert '"membership-multi-b"' in SOURCE


def test_dev_fixture_covers_the_full_project_lifecycle() -> None:
    for slug in (
        "borrador",
        "cotizado",
        "enviado",
        "aprobado",
        "conjuntos",
        "portal",
        "vitrina",
        "despachado",
        "instalado",
        "rechazado",
        "expirada",
        "escala",
    ):
        assert f'("{slug}", ' in SOURCE
    # 100-position project feeds list/canvas scale surfaces.
    assert "for i in range(1, 101):" in SOURCE


def test_dev_fixture_seeds_clients_with_chilean_contact_data() -> None:
    assert SOURCE.count("@") >= 8  # real-looking .cl contact e-mails
    assert "make_rut(" in SOURCE  # valid módulo-11 tax ids, not literals


def test_dev_fixture_keeps_idempotent_write_patterns() -> None:
    assert 'Prefer": "resolution=merge-duplicates,return=representation"' in SOURCE
    assert "ON CONFLICT (cost_list_id, sku) DO NOTHING" in SOURCE
    assert "ON CONFLICT (org_id,sku,variant_key) DO NOTHING" in SOURCE
    # Deterministic ids: every row id derives from the fixture namespace.
    assert "uuid.uuid5(NS," in SOURCE
