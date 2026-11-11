from snap_assistant import CardPool, Deck
from snap_assistant.analysis import analyze, energy_curve, suggest

pool = CardPool.load()


def deck(*names):
    return Deck("t", [pool.get(n) for n in names])


def test_pool_lookup_case_insensitive():
    assert pool.get("knull").name == "Knull"
    assert "VISION" in pool


def test_deck_size_and_duplicates():
    d = deck("Knull", "Knull")
    errs = d.validate()
    assert any("exactly 12" in e for e in errs)
    assert any("Duplicate" in e for e in errs)


def test_valid_deck():
    names = [c.name for c in pool][:12]
    assert deck(*names).is_valid


def test_curve_groups_six_plus():
    assert energy_curve([pool.get("Death"), pool.get("Knull")])[6] == 2


def test_analyze_flags_no_early_game():
    r = analyze(deck("Death", "Knull", "Heimdall"))
    assert any("early" in w for w in r.warnings)


def test_suggest_prefers_synergy():
    d = deck("Carnage", "Deathlok", "Venom", "Bucky Barnes")
    names = [c.name for c, _ in suggest(d, pool, limit=5)]
    assert names and all(n not in {"Carnage", "Deathlok", "Venom", "Bucky Barnes"} for n in names)
    top = pool.get(names[0])
    assert "destroy" in top.tags
