from pathlib import Path

from garmin_sync import dashboard, sample


def test_sample_is_deterministic_and_fictional(tmp_path: Path):
    j1 = sample.generate(tmp_path / "a")
    j2 = sample.generate(tmp_path / "b")
    a = sorted(p.read_text(encoding="utf-8") for p in (tmp_path / "a").rglob("*.json"))
    b = sorted(p.read_text(encoding="utf-8") for p in (tmp_path / "b").rglob("*.json"))
    assert a == b and len(a) > 1000
    assert all(p.name.startswith(("2029", "2030")) for p in (tmp_path / "a").rglob("*.json"))
    assert any("party" in e.tags for e in j1.entries.values())
    assert j1.periods == j2.periods


def test_sample_dashboard_links_to_guide(tmp_path: Path):
    j = sample.generate(tmp_path / "data")
    md = dashboard.build(tmp_path / "data", tmp_path / "out", sample.TODAY, j, guide="../charts.md")
    assert "[chart guide](../charts.md)" in md
    assert "(../charts.md#hrv)" in md
