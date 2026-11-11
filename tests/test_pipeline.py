"""Pipeline tests using small fake payloads in each site's real JSON shape."""
import copy
import json

import pytest

from snap_assistant import CardPool
from snap_assistant.cli import main
from snap_assistant.pipeline.sources import MARVELSNAP_PRO, MARVELSNAPZONE
from snap_assistant.pipeline.store import Store
from snap_assistant.pipeline.sync import SanityRules, sync
from snap_assistant.pipeline.tags import derive_tags
from snap_assistant.pipeline.text import clean_text

RULES = SanityRules(min_count={"card": 1, "location": 1})
SOURCES = [MARVELSNAP_PRO, MARVELSNAPZONE]


def pro_card(def_id, name, cost, power, text, *, used=True, token=False, type_="Character",
             series="Series3", patch="42.6.2"):
    return {"CardDefId": def_id, "name": name, "cost": str(cost), "power": str(power),
            "description": text, "use_count": "5" if used else "0", "is_Token": "1" if token else "0",
            "type": type_, "CardSeriesDefId": series, "wasChangedIn": patch, "wasAddedIn": ""}


def zone_card(def_id, name, cost, power, text, *, released=True, type_="Character"):
    return {"carddefid": def_id, "name": name, "cost": cost, "power": power, "ability": text,
            "type": type_, "status": "released" if released else "unreleased", "art": ""}


def base_payloads():
    pro_cards = {
        "knull": pro_card("Knull", "Knull", 6, 0, "<b>Ongoing:</b> Has the combined Power of all cards destroyed this game."),
        "batroc": pro_card("Batroc", "Batroc", 3, 3, "When a card moves, follow it to gain +2 Power. <i>(once per turn)</i>"),
        "hulk": pro_card("Hulk", "Hulk", 6, 12, '<i>"HULK SMASH!"</i>', series="Starter"),
        "evolvedhulk": pro_card("EvolvedHulk", "Hulk", 6, 14, "", token=True, used=False, series="None"),
        "carnagechampion": pro_card("CarnageChampion", "Carnage Champion", 2, 2, "<b>On Reveal:</b> Destroy.", series="None"),
        "spidersense": pro_card("SpiderSense", "Spider Sense", 5, 0, "<b>On Reveal:</b> Buff.", type_="Skill"),
        "newguy": pro_card("NewGuy", "New Guy", 2, 2, "", used=False),
    }
    zone_cards = {"success": {"cards": [
        zone_card("Knull", "Knull", 6, 0, "<span>Ongoing</span>: Has the combined Power of all cards destroyed this game."),
        zone_card("Batroc", "Batroc", 3, 3, ""),  # the Zone leaves some text blank
        zone_card("Hulk", "Hulk", 6, 12, ""),
        zone_card("EvolvedHulk", "Evolved Hulk", 6, 14, "", released=False),
        zone_card("CarnageChampion", "Carnage Champion", 2, 2, "<span>On Reveal</span>: Destroy."),
        zone_card("SpiderSense", "Spider Sense", 5, 0, "<span>On Reveal</span>: Buff."),
        zone_card("NewGuy", "New Guy", 2, 2, "", released=False),
        zone_card("ZoneOnly", "Zone Only", 1, 2, ""),
    ]}}
    pro_locs = {"altar": {"CardDefId": "AltarOfDeath", "name": "Altar of Death",
                          "description": "After you play a card here, destroy it to get +2 Energy next turn.",
                          "released": "1", "wasChangedIn": "", "wasAddedIn": "", "rarity": "Rare"}}
    zone_locs = {"success": {"cards": [
        {"carddefid": "AltarOfDeath", "name": "Altar of Death", "type": "Location", "status": "released",
         "ability": "After you play a card here, destroy it to get +2 Energy next turn."}]}}
    return {
        MARVELSNAP_PRO.urls["card"]: pro_cards, MARVELSNAP_PRO.urls["location"]: pro_locs,
        MARVELSNAPZONE.urls["card"]: zone_cards, MARVELSNAPZONE.urls["location"]: zone_locs,
    }


def fetcher(payloads, down=()):
    def fetch(url):
        if any(url.startswith(f"https://{d}") for d in down):
            raise RuntimeError("connection refused")
        return copy.deepcopy(payloads[url])
    return fetch


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "snap.db")
    yield s
    s.close()


def run(store, payloads, **kw):
    return sync(store, SOURCES, fetcher(payloads, kw.pop("down", ())), rules=RULES, **kw)


def row(store, def_id, kind="card"):
    return store.db.execute("SELECT * FROM entities WHERE kind=? AND def_id=?", (kind, def_id)).fetchone()


def set_pro_power(p, key, power, patch):
    p[MARVELSNAP_PRO.urls["card"]][key].update(power=str(power), wasChangedIn=patch)


def set_zone_power(p, def_id, power):
    for c in p[MARVELSNAPZONE.urls["card"]]["success"]["cards"]:
        if c["carddefid"] == def_id:
            c["power"] = power


# --- text & tags -----------------------------------------------------------

def test_clean_text_makes_sources_comparable():
    assert clean_text("<b>On Reveal:</b> Do it. <i>(once per turn)</i>") == \
        clean_text("<span>On Reveal</span>: Do it. (once per turn)")
    assert clean_text("It’s  <color=#fff>fine</color>") == "It's fine"
    assert clean_text('<i>"HULK SMASH!"</i>') == ""   # flavour quote, not an ability


def test_derive_tags():
    assert {"on-reveal", "destroy"} <= derive_tags("On Reveal: Destroy your other cards here.")
    assert "ongoing" in derive_tags("Ongoing: Your cards here have +1 Power.")
    assert "move" in derive_tags("You can move this once.")
    assert "discard" in derive_tags("On Reveal: Discard a card from your hand.")
    assert "afflict" in derive_tags("On Reveal: Give a random enemy card -2 Power.")
    assert "vanilla" in derive_tags("", 6, 12)
    assert "zoo" in derive_tags("", 1, 2)


# --- first sync ----------------------------------------------------------

def test_first_sync_confirms_agreeing_sources(store):
    r = run(store, base_payloads())
    assert r.status == "ok"
    knull = row(store, "Knull")
    assert knull["status"] == "confirmed" and knull["power"] == 0
    assert knull["text"] == "Ongoing: Has the combined Power of all cards destroyed this game."
    assert set(json.loads(knull["tags"])) >= {"ongoing", "destroy"}
    assert row(store, "ZoneOnly")["status"] == "provisional"
    assert row(store, "AltarOfDeath", "location")["status"] == "confirmed"
    assert r.game_patch == "42.6.2"


def test_blank_text_on_one_source_is_not_a_conflict(store):
    run(store, base_payloads())
    batroc = row(store, "Batroc")
    assert batroc["status"] == "confirmed"
    assert batroc["text"].startswith("When a card moves")


def test_token_name_labels_do_not_conflict(store):
    run(store, base_payloads())
    evolved = row(store, "EvolvedHulk")
    assert evolved["status"] == "confirmed" and evolved["name"] == "Hulk"
    assert store.issues() == []


def test_released_if_either_source_says_so(store):
    p = base_payloads()
    run(store, p)
    assert row(store, "NewGuy")["released"] == 0
    # Release day: the Zone flips first, marvelsnap.pro has no plays yet.
    for c in p[MARVELSNAPZONE.urls["card"]]["success"]["cards"]:
        if c["carddefid"] == "NewGuy":
            c["status"] = "released"
    run(store, p)
    assert row(store, "NewGuy")["released"] == 1


def test_second_identical_sync_reports_no_changes(store):
    run(store, base_payloads())
    r = run(store, base_payloads())
    assert not any(d.touched for d in r.decisions)
    assert "No changes." in r.report
    assert not r.noteworthy


# --- balance patch arriving at different times ------------------------------

def test_patch_lag_is_held_as_conflict_then_confirmed(store):
    p = base_payloads()
    run(store, p)

    set_pro_power(p, "knull", 2, "58.15.2")            # marvelsnap.pro updates first
    r = run(store, p)
    assert row(store, "Knull")["power"] == 0            # old value kept
    assert row(store, "Knull")["status"] == "conflict"
    assert r.new_issue_count == 1 and r.noteworthy
    assert "Conflicts" in r.report

    r = run(store, p)                                    # still disagreeing: not "new" again
    assert r.new_issue_count == 0

    set_zone_power(p, "Knull", 2)                         # the Zone catches up
    r = run(store, p)
    knull = row(store, "Knull")
    assert knull["power"] == 2 and knull["status"] == "confirmed"
    assert store.issues() == []
    hist = [h for h in store.history("card", "Knull") if h["field"] == "power"]
    assert [(h["old"], h["new"], h["how"], h["patch"]) for h in hist] == [("0", "2", "confirmed", "58.15.2")]
    assert "Knull" in r.report and "0 → 2" in r.report


def test_source_down_holds_changes_to_confirmed_fields(store):
    p = base_payloads()
    run(store, p)
    set_pro_power(p, "knull", 2, "58.15.2")
    r = run(store, p, down=("marvelsnapzone.com",))
    assert r.status == "partial"
    knull = row(store, "Knull")
    assert knull["power"] == 0 and knull["status"] == "pending"
    assert json.loads(knull["sources"]) == ["marvelsnap.pro", "marvelsnapzone.com"]
    assert "Awaiting confirmation" in r.report


def test_single_source_field_updates_without_confirmation(store):
    p = base_payloads()
    run(store, p)
    p[MARVELSNAP_PRO.urls["card"]]["batroc"]["description"] = "When a card moves, follow it to gain +3 Power."
    run(store, p)
    batroc = row(store, "Batroc")
    assert "+3 Power" in batroc["text"]
    assert [h["how"] for h in store.history("card", "Batroc") if h["field"] == "text"] == ["single-source"]


# --- bad data ----------------------------------------------------------------

def test_shrunken_source_is_rejected(store):
    p = base_payloads()
    run(store, p)
    pro = p[MARVELSNAP_PRO.urls["card"]]
    for k in list(pro)[:4]:
        del pro[k]
    r = run(store, p)
    pro_result = next(s for s in r.sources if s.name == "marvelsnap.pro")
    assert not pro_result.ok and "dropped" in pro_result.error
    assert r.status == "partial"
    assert row(store, "Knull") is not None


def test_all_sources_down_changes_nothing(store):
    run(store, base_payloads())
    before = store.db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    r = run(store, base_payloads(), down=("marvelsnap.pro", "marvelsnapzone.com"))
    assert r.status == "failed" and r.noteworthy
    assert store.db.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == before
    assert "nothing was changed" in r.report


def test_dry_run_writes_nothing(store):
    r = run(store, base_payloads(), dry_run=True)
    assert r.status.startswith("dry-run")
    assert not store.has_data()


# --- overrides ------------------------------------------------------------

def test_override_wins_and_is_reported_stale_once_sources_agree(store):
    p = base_payloads()
    run(store, p)
    ov = {"card": {"Knull": {"power": 2, "tags_add": ["control"]}}}
    run(store, p, overrides=ov)
    knull = row(store, "Knull")
    assert knull["power"] == 2 and "control" in json.loads(knull["tags"])

    set_pro_power(p, "knull", 2, "58.15.2")
    set_zone_power(p, "Knull", 2)
    r = run(store, p, overrides=ov)
    assert "safe to remove" in r.report


# --- card pool ------------------------------------------------------------

def test_pool_from_db_has_only_deck_buildable_cards(store, tmp_path):
    run(store, base_payloads())
    pool = CardPool.from_db(tmp_path / "snap.db")
    names = {c.name for c in pool}
    assert {"Knull", "Batroc", "Hulk", "Zone Only"} <= names
    # token, game-mode Champion, Skill, unreleased
    assert not names & {"Carnage Champion", "Spider Sense", "New Guy"}
    assert len([c for c in pool if c.name == "Hulk"]) == 1 and pool.get("hulk").power == 12
    assert pool.get("knull") is pool.get("Knull")


def test_lookup_ignores_punctuation():
    pool = CardPool.load()
    assert pool.get("ant man") is pool.get("Ant-Man")


def test_cli_reads_database(store, tmp_path, capsys):
    run(store, base_payloads())
    db = str(tmp_path / "snap.db")
    assert main(["--db", db, "show", "knull"]) == 0
    out = capsys.readouterr().out
    assert "Cost 6  Power 0" in out and "confirmed" in out
    main(["--db", db, "locations"])
    assert "Altar of Death" in capsys.readouterr().out
    main(["--db", db, "issues"])
    assert "No open conflicts" in capsys.readouterr().out
