from pathlib import Path


SOURCE = Path(__file__).with_name("dev_fixture.py").read_text(encoding="utf-8")


def test_dev_fixture_declares_two_realistic_organizations() -> None:
    assert 'ORG_NAME = "Ventanas del Sur SpA"' in SOURCE
    assert 'ORG_B_NAME = "Cristales Bio Bio Ltda."' in SOURCE
    assert '"tax_id": "76.543.210-3"' in SOURCE
    assert '"tax_id": "77.123.456-9"' in SOURCE


def test_dev_fixture_has_required_realistic_client_and_project_volume() -> None:
    assert SOURCE.count("example.cl") >= 6
    assert 'for i in range(1, 101):' in SOURCE
    assert '"CASA_LOMAS"' in SOURCE
    assert '"TORRE_BARROS"' in SOURCE
    assert 'mark_project_phases(' in SOURCE


def test_dev_fixture_keeps_idempotent_write_patterns() -> None:
    assert 'Prefer": "resolution=merge-duplicates,return=representation"' in SOURCE
    assert "ON CONFLICT (cost_list_id,sku) DO NOTHING" in SOURCE
    assert "ON CONFLICT (org_id,sku,variant_key) DO NOTHING" in SOURCE
    assert "regexp_replace(COALESCE(notes_internal,'')," in SOURCE
