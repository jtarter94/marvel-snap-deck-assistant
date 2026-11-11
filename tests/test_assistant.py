"""Rules reference, assistant queries and the MCP server, against a fixture database."""
import asyncio
import json

import pytest

from snap_assistant import assistant as A
from snap_assistant import knowledge
from snap_assistant.pipeline.sources import bold_keywords
from snap_assistant.pipeline.store import Store
from snap_assistant.pipeline.sync import uncovered_keywords

from test_pipeline import base_payloads, run


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "snap.db")
    run(s, base_payloads())
    yield s
    s.close()


# --- rules reference -------------------------------------------------------

def test_every_section_has_status_and_body():
    secs = knowledge.sections()
    assert len(secs) > 20
    for s in secs:
        assert s.status in ("established", "from-card-text"), s.title
        assert s.body.strip(), s.title


def test_lookup_by_title_alias_and_text():
    assert [s.title for s in knowledge.lookup("ongoing")] == ["Ongoing"]
    assert knowledge.lookup("back-row")[0].title == "Front row and back row"
    assert knowledge.lookup("horde +3")[0].title == "Horde"
    assert any(s.title == "Counters and protection" for s in knowledge.lookup("cosmo"))


def test_bold_keywords_and_coverage():
    assert bold_keywords("<b>On Reveal and When Destroyed:</b> <b>Horde +3</b>.") == \
        ["On Reveal", "When Destroyed", "Horde"]
    assert bold_keywords("<b>When Discarded or Destroyed:</b> x") == ["When Discarded or Destroyed"]
    for k in ("On Reveal", "Ongoing", "Activate", "Moveable", "Objective", "Quickdraw", "Empowered",
              "Frontline", "Backline", "Infect", "Start of Turn", "On Reveals"):
        assert knowledge.covers(k), k
    assert not knowledge.covers("Overload")


def test_sync_reports_unknown_keywords(tmp_path):
    p = base_payloads()
    from snap_assistant.pipeline.sources import MARVELSNAP_PRO
    p[MARVELSNAP_PRO.urls["card"]]["knull"]["description"] = "<b>Overload:</b> Something new."
    s = Store(tmp_path / "x.db")
    r = run(s, p)
    assert "Overload" in r.uncovered_keywords
    assert "Keywords missing from the rules reference" in r.report
    s.close()


def test_eval_questions_reference_real_sections():
    titles = {s.title for s in knowledge.sections()}
    qs = A.eval_questions()
    assert len({q["id"] for q in qs}) == len(qs)
    for q in qs:
        assert q["question"] and q["expected"]
        assert set(q["rules"]) <= titles, q["id"]


# --- assistant queries -------------------------------------------------------

def test_resolve_tolerates_typos_and_punctuation(store):
    assert A.resolve(store, "knul")["def_id"] == "Knull"
    assert A.resolve(store, "vampire-killmonger")["def_id"] == "VampireKillmonger"
    with pytest.raises(A.NotFound, match="No card"):
        A.resolve(store, "zzzz")


def test_search_filters(store):
    out = A.search_cards(store, tag="destroy")
    assert "Knull" in out and "Carnage Champion" not in out          # game-mode version excluded
    assert "Carnage Champion" in A.search_cards(store, text="destroy", include_non_deck=True)
    assert "Polymorph" in A.search_cards(store, pool="all-skills", include_non_deck=True)
    assert A.search_cards(store, text="nothing like this") == "No matching cards."
    assert "Vampire Killmonger" in A.search_cards(store, released_after="2026-01-01")


def test_collection_and_owned_filters(store):
    assert "No collection recorded" in A.collection_summary(store)
    assert "Knull" in A.search_cards(store, owned="unowned")
    A.set_owned(store, ["Knull", "Hulk"])
    assert "You own 2 of" in A.collection_summary(store)
    owned = A.search_cards(store, owned="owned")
    assert "Knull" in owned and "Batroc" not in owned
    assert "Knull" not in A.search_cards(store, owned="unowned")
    assert "✓owned" in A.describe_card(store, "Knull")
    deck = A.analyze_deck(store, ["Knull", "Batroc"])
    assert "Not owned (1): Batroc" in deck


def test_analyze_deck_flags_non_deck_cards_and_links(store):
    out = A.analyze_deck(store, ["Merlin", "Scarlet Witch Queen of Chaos", "Polymorph"])
    assert "Polymorph can't go in a deck" in out
    assert "Merlin → Polymorph" in out
    assert "Scarlet Witch Queen of Chaos generates All Skills" in out


def test_saved_decks(store):
    A.save_deck(store, "Chaos", ["Merlin", "Scarlet Witch Queen of Chaos"], "skills matter")
    assert "Chaos" in A.list_decks(store) and "skills matter" in A.list_decks(store)
    shown = A.show_deck(store, "chaos")
    assert "Notes: skills matter" in shown and "Merlin" in shown
    A.save_deck(store, "Chaos", ["Merlin"])                 # overwrite keeps notes
    assert "1 cards" in A.list_decks(store) and "skills matter" in A.list_decks(store)


def test_random_cards_is_reproducible(store):
    assert A.random_cards(store, 3, seed=7) == A.random_cards(store, 3, seed=7)


def test_check_evals_flags_changed_text(store):
    out = A.check_evals(store)   # fixture lacks most eval cards -> reported, not crashing
    assert "questions" in out and "STALE" in out


# --- MCP server --------------------------------------------------------------

def test_mcp_tools(store, monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.setenv("SNAP_ASSISTANT_DB", str(store.path))
    from snap_assistant import mcp_server

    tools = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert {"search_cards", "get_card", "rules", "analyze_deck", "set_owned", "save_deck",
            "list_pools", "get_pool", "random_cards"} <= tools
    assert "Generates from: All Skills" in mcp_server.get_card("Scarlet Witch Queen of Chaos")
    assert "No card named" in mcp_server.get_card("zzzz")
    assert "Merge" in mcp_server.rules("merge")
    assert "Marked 1 card" in mcp_server.set_owned(["Knull"])
