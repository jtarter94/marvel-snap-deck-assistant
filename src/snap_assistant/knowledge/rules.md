# Marvel Snap rules reference

How the game works, for reasoning about decks and interactions. Card and
location **text** always comes from the synced database (it changes with
patches); this file covers the rules that text is interpreted against.

Each section has a metadata line:

- `status: established`: long-standing core rule.
- `status: from-card-text`: worked out from how current cards use the term;
  check in-game before relying on edge cases, then promote it.
- `aliases:` other words that should find the section.
- `verified:` patch or date someone checked it in-game, when they have.

Sections under **Keywords** must cover every bolded keyword the card data
uses; `snap-assistant sync` reports any that are missing.

# Core rules

## Deck and collection
`status: established` · `aliases: deck building, deck size, duplicates, collection`

- A deck is exactly 12 cards with no duplicates (different art variants of the
  same card count as the same card).
- Deck cards are collectible **characters** and collectible **Skills** (see
  Skills). Tokens, generated Skills (e.g. Polymorph, Vampiric Spear),
  Augments, Trinkets, game-mode versions ("X - Brotherhood of Mutants",
  "X Champion") and other created cards can't go in a deck; they appear
  through card effects or game modes.
- Cards in your deck at the start of a game are your "original" cards; anything
  added during the game is a **created** card (see Created cards).

## Game flow
`status: established` · `aliases: turns, turn order, game length, hand size, draw`

- A game lasts 6 turns unless an effect changes that (some locations/cards
  add or remove turns).
- You start with 3 cards in hand and draw 1 at the start of each turn, so you
  have 4 on turn 1. Maximum hand size is 7; draws beyond that are lost.
- Both players play cards **simultaneously** and face down; the other player
  doesn't see what you played until cards reveal at the end of the turn.
- Order of a turn: Start of Turn effects → both players play cards (and use
  Activate / Moveable abilities) → both end the turn → cards reveal → End of
  Turn effects.

## Energy
`status: established` · `aliases: mana, max energy, unspent energy, ramp`

- Your Max Energy equals the turn number (1 on turn 1 … 6 on turn 6) unless
  effects raise it. Energy refills every turn; unspent Energy does not carry
  over (but some cards reward or check unspent Energy).
- "+1 Energy next turn" is a one-turn bonus; "+1 Max Energy" is permanent.

## Cost vs cost
`status: established` · `aliases: base cost, current cost, printed cost, x-Cost, even-costed, odd-costed, cost check` · `verified: player, 2026-11-11`

- Card text distinguishes **Cost** (capital C) from **cost** (lowercase c).
- **Cost** means the card's base Cost. Discounts don't change it, so a card
  checking "5-Cost or more" (Chamber, Mordred's "higher-Cost", Excalibur's
  "4-Cost or more") still sees Valentina's 6-Cost card after its −2, and still
  sees The Grand Design as 6-Cost however cheap it has become.
- **cost** means the Energy it currently takes to play the card, after
  discounts such as Quinjet or Mother Askani's copy (e.g. Moon Knight's
  "even-costed").

## Locations
`status: established` · `aliases: location reveal, location effects, lanes`

- There are 3 locations. They start hidden and reveal one per turn: left on
  turn 1, middle on turn 2, right on turn 3.
- Each player can have at most 4 cards at a location.
- A location's text applies while it's in play. Some cards replace or destroy
  locations.

## Front row and back row
`status: established` · `aliases: front row, back row, front-row, back-row, in front of, behind, full front row` · `verified: player, 2026-11-11`

- A player's side of each location has 4 slots arranged as a front row and a
  back row. Card text refers to "front-row cards", "back-row cards", and "the
  card in front of this" (e.g. Captain Carter: "Add this card's Power to your
  back-row cards here"; Cosmic Ghost Rider: "Remove the text from front-row
  enemy cards here"; Prodigy: "If this is in the back row, copy the text of
  the card in front of it").
- The first two cards placed at a location fill the
  front row and the next two the back row, with each back-row slot behind a
  front-row slot.

## Revealing and priority
`status: established` · `aliases: reveal order, priority, who reveals first, reveal phase`

- At the end of a turn, cards reveal one at a time in the order they were
  played, all of one player's cards first.
- The player **winning more locations** reveals first; if tied, the player
  with more total Power across all locations; if still tied, it's random.
  (The game highlights the player who will reveal first.)
- Order matters: a card's On Reveal only sees cards already revealed. Cards
  that "check what your opponent played" or "the last card you played" depend
  on this.

## Winning
`status: established` · `aliases: win condition, tie, total power, locations won`

- After the last turn, whoever has more Power at a location wins it. Win 2 of
  3 locations to win the game.
- If locations are split (e.g. 1–1 with a tie), the player with more total
  Power across all locations wins; if that's tied too, the game is a draw.

## Cubes and Snap
`status: established` · `aliases: cubes, snapping, retreat, ranked stakes`

- Games are played for cubes (ranked stakes). The stakes start at 1 and double
  when either player Snaps, and double again automatically before the final
  turn. Retreating ends the game and loses only the current stakes.
- Snapping is a strategic decision only; it doesn't affect deck building.

## Power
`status: established` · `aliases: power, buff, base power, original power, reduce power, negative power`

- A location's score is the total Power of your cards there. Cards can have
  negative Power.
- A card's Power can be changed permanently (On Reveal buffs, afflictions,
  stealing) or continuously (Ongoing effects, which are recalculated whenever
  the board changes and disappear if their source leaves or loses its text).
- "Original" or "base" Power is the card's printed Power; Shadow King-style
  effects reset to it, removing permanent and continuous changes.
- Power gained in hand or deck stays with the card when it's played.
- **Inverting** Power (The Inversion) multiplies it by −1; the game shows it
  as "x-1", not as a Power change. A card inverted to negative Power is **not**
  "afflicted" (see Afflict), and The Inversion's "card(s) here" includes enemy
  cards (verified: player, 2026-11-11).

## Skills
`status: established` · `aliases: skill, skills, skill card, spell, banished after use` · `verified: player, 2026-11-11`

- Skills are cards with a Cost and an ability but no character (they show 0
  Power), e.g. The Inversion, Web Sling, Fastball Special, Astral Projection.
  Most of their text is an On Reveal.
- A Skill is **banished once it's played**: it resolves and disappears. It
  doesn't stay at the location, so it doesn't take one of the 4 slots, add
  Power, or count as a card there afterwards. Because banishing isn't
  destroying or discarding, it doesn't feed destroy/discard counters (Knull,
  Death) or trigger "When Destroyed" effects.
- Some Skills are **collectible** (they belong to a collection series and go
  in decks like characters); others are only **generated** by cards (Merlin's
  Incantations, Vampire Killmonger's Vampiric Spear) or by game modes.
- Text that says "character" doesn't include Skills; text that says "card"
  does (e.g. Polymorph transforms a character; Quinjet's "created cards"
  includes generated Skills).
- Deck-building consequence: Skills are effects, not board presence. They're
  good for filling a location's slots without spending them, and poor in
  decks that want many cards on the board or count cards at a location.

## Created cards
`status: established` · `aliases: created, generated, tokens, add to hand, copies`

- Any card added during the game (tokens like Rocks or Drones, Skills, copies
  of other cards) is "created". Effects that care about created cards
  (e.g. Quinjet: "Your created cards cost 1 less") include them all.
- In this database, cards that other cards make are linked with `creates`, and
  pools such as **All Skills** list what a "random X" effect can produce.

# Keywords

## On Reveal
`status: established` · `aliases: on reveals, on-reveal, reveal ability`

- Happens when the card reveals after being **played**, and also when it
  comes back into play by being **revived, resurrected or regenerated**
  (verified by the player; see Revive, Resurrect and Regenerate). Moving a
  card doesn't trigger it.
- A card **put into play from hand by an effect** (Dragon Lord: "Put a card
  from your hand here"; Eson: "Put a created card from your hand here") also
  triggers its On Reveal, but it doesn't count as **played**: it doesn't
  count for "per card played" discounts (The Grand Design) or "play N cards"
  Objectives (Stryfe) (verified: player, 2026-11-11).
- Eson picks at random when you hold several created cards (verified:
  player, 2026-11-11).
- Can be repeated by effects (Wong: "Your On Reveal abilities here repeat";
  Odin repeats the On Reveals of your other cards at his location), copied, or
  prevented (Cosmo: "On Reveal abilities won't happen here").
- Text that is removed before the card reveals means nothing happens
  (Alioth removes the text of unrevealed enemy characters).

## Ongoing
`status: established` · `aliases: continuous, ongoing effect, static`

- Applies continuously while the card is in play and still has its text.
  Effects update immediately when the board changes.
- Ends when the card leaves play or loses its abilities (Enchantress removes
  the abilities of all Ongoing cards at her location; Echo removes abilities
  from Ongoing cards the opponent plays at hers).
- Two copies of an Ongoing effect (e.g. a Mystique copying it) both apply.

## Activate
`status: established` · `aliases: activated ability, activation` · `verified: player, 2026-11-11`

- An ability you choose to use once per game by tapping the card while it's in
  play. It doesn't cost Energy.
- It resolves at the end of the turn alongside revealing cards, in the same
  priority order.
- It can't be used until the turn after the card is
  revealed (cards reveal at the end of the turn they're played).

## End of Turn
`status: established` · `aliases: end of each turn, at the end of turn`

- Triggers after cards have revealed at the end of every turn while the card
  is in play, including the turn it was played.

## Start of Turn
`status: established` · `aliases: start of each turn, beginning of turn` · `verified: player, 2026-11-11`

- Triggers at the start of each turn while the card is in play (e.g. Merlin:
  "Start of Turn: Add an Incantation to your hand"). The turn it's played it
  hasn't triggered yet; it first triggers the following turn.

## Game Start
`status: established` · `aliases: start of game, game-start`

- Triggers once at the beginning of the game if the card is in your **deck**
  (it works whether or not you ever draw it), e.g. Arishem shuffles 12 cards
  into your deck.

## When Discarded
`status: established` · `aliases: when discarded, on discard, discard trigger`

- Triggers when the card is discarded from your hand by an effect.
- **Discard** means moving a card from hand to the discard pile. It's
  different from destroying (cards in play) and banishing.

## When Destroyed
`status: established` · `aliases: when destroyed, on destroy, death trigger`

- Triggers when the card is destroyed while in play.
- **Destroy** removes a card in play (or in some text, in hand/deck) to the
  destroyed pile. Cards that care about "destroyed this game" (Knull, Death)
  count every destroyed card, yours and your opponent's, unless they say
  otherwise.

## When Discarded or Destroyed
`status: established` · `aliases: discarded or destroyed`

- Triggers on either event (e.g. Wolverine regenerates; Marrow splits -7 Power
  among enemy cards).

## Moveable
`status: established` · `aliases: move, moveable once, can move, moves, moved`

- A Moveable card can be moved by you to another location during your turn
  (it costs no Energy). "Moveable once" means one time per game; plain
  "Moveable" means once per turn.
- Moving doesn't re-trigger On Reveal. Cards that say "When this moves" or
  "When a card moves" trigger on any move, including moves caused by other
  effects.
- Cards can also be moved by effects (e.g. Cloak, Madame Web) without being
  Moveable themselves. Professor X's location only lets characters leave or
  arrive by moving.

## Objective
`status: established` · `aliases: objective, objectives, horseman` · `verified: player, 2026-11-11`

- A goal with a progress counter shown in brackets, e.g. Archangel Horseman of
  Death: "Objective: Your cards are destroyed 4 times — Resurrect one here
  with +5 Power. (0/4)". When the counter is complete the reward happens.
- Progress counts while the card is in your **hand or deck**, not only in
  play, so an Objective can be partly or fully done before you play the card.
- A reward completed while the card is in hand or deck waits: it goes off
  only after you play the card, at the end of the turn you play it, and
  "here" is where the card was played. E.g. Stryfe with his Objective done in
  hand, played on turn 5, uses his On Reveal at the end of turn 5 (verified:
  player, 2026-11-11).
- An Objective completes once per game (player's understanding; whether a
  revived or copied card can complete it again is unconfirmed).
- When an Objective reward picks "the highest-Cost" card and several are tied,
  the game picks one of them at random (e.g. Stryfe with two 6-Cost On Reveal
  cards in hand; verified: player, 2026-11-11).

## Horde
`status: established` · `aliases: zombie horde, horde +1, horde +2, horde +3, horde +4` · `verified: player, 2026-11-11`

- "Horde +N" gives your **Zombie Horde** N Power ("Give your Zombie Horde that
  much Power"). If you don't have a Zombie Horde yet, it is created first
  ("Horde first if necessary").
- The Zombie Horde is a created card; cards like Zombie Giant-Man scale with it.

## Quickdraw
`status: established` · `aliases: quickdraw, quick draw` · `verified: player, 2026-11-11`

- An extra effect that replaces or adds to the card's normal effect under a
  condition (Red Hulk Fractured Frontier: "On Reveal: -1 Power for each enemy
  card here. Quickdraw: +1 Power instead").
- The Quickdraw condition is playing the card on the
  same turn you drew it. Thanos Fractured Frontier gives all your cards a
  Quickdraw at Game Start.

## Empowered
`status: established` · `aliases: empower, empowered, when this is empowered` · `verified: player, 2026-11-11`

- A card is Empowered when an effect increases its Power. Cards trigger "When
  this is Empowered" whether in hand, deck or play when their text says so
  (Sebastian Shaw: "gain an additional +2 Power (if in hand, in deck, or in
  play)"; Venus adds +1 more when your cards in play are Empowered).
- **Ongoing Power doesn't count.** Only effects that actually give Power
  (On Reveals, End of Turn buffs, etc.) Empower a card; continuous bonuses
  from Ongoing cards don't trigger "When Empowered".

## Frontline and Backline
`status: established` · `aliases: frontline, backline, duo cards, doomsday` · `verified: player, 2026-11-11`

- Cards with two halves (the Doomsday duo cards, e.g. "Gambit & Shang-Chi
  Doomsday: Frontline | On Reveal: … Backline | On Reveal: …"). The half that
  applies depends on whether the card is in the front row or the back row
  (see Front row and back row).
- The Doomsday duo cards aren't released yet in the current data; recheck
  their text when they arrive.

## Infect
`status: established` · `aliases: infect, infected` · `verified: player, 2026-11-11`

- Replaces the text of the infected cards with the infecting card's text
  (Techno-Organic Virus: "Infect your other cards here (replace their text)").

## Judge
`status: established` · `aliases: judge, worthy, jane foster` · `verified: player, 2026-11-11`

- Only used by Jane Foster Fractured Frontier: "Judge 4 other random
  characters. +1 Power (if yours) or -1 Power (enemies). Quickdraw: Judge
  the worthy again."
- Each judgement picks 4 random characters fresh and applies its +1/-1 to
  each of them. Every repeat (her Quickdraw, Wong, Odin, a copy) picks a new
  random set, so the same card can be judged more than once.

# Common mechanics (not bolded keywords)

## Afflict
`status: established` · `aliases: afflict, afflicted, negative power, -power, reduce`

- Giving a card negative Power (e.g. Hazmat: "Afflict all other cards with
  -1 Power"). Afflicting your own cards is a deliberate strategy with cards
  that reward negative Power (Ajax, Diamondback).
- Luke Cage prevents your front-row cards' Power from being reduced.
- Inverting isn't afflicting: a card that's negative only because its Power
  was inverted ("x-1", e.g. The Inversion) doesn't count as "afflicted with
  negative Power" for Ikari, Ajax or Diamondback (verified: player, 2026-11-11).
- Afflictions put on cards in hand (e.g. Scorpion, Selene) stay on the card
  when it's played, so it's still afflicted on the board and counts for Ikari,
  Ajax and Diamondback (verified: player, 2026-11-11).

## Steal
`status: established` · `aliases: steal, stealing, stolen power`

- Takes Power from a card and adds the same amount to the stealing card.

## Merge
`status: established` · `aliases: merge, merged, merging, symbiote spider-man` · `verified: player, 2026-11-11`

- One card is merged into another: the merged card leaves play and the card it
  merges into gains its Power (Hulkbuster: "Merge this into one of your cards
  here"). Some cards care about merging (Strange Supreme: "Gains +2 Power from
  merging"; Peni Parker gives +1 Energy when it merges).
- Abilities are not combined unless the card's text says so. Symbiote
  Spider-Man's does ("Merge your lowest-Cost card here into this. Copy its
  text like it just revealed"), so it takes on the merged card's text
  (verified by the player, 2026-11-11):
  - **On Reveal** happens again, as if it just revealed (a merged Galactus
    re-checks its condition and can destroy the other locations again).
  - **Ongoing** is kept and keeps applying (a merged Onslaught keeps making
    your other Ongoing effects there apply an additional time).
  - **Objective / Activate** keep their state: a completed Objective or an
    already-used Activate stays completed/used. The merge doesn't reset it.
  - It picks the *lowest-Cost* card at its location, so setting up a specific
    target (e.g. Galactus) means having nothing cheaper there.
- **Only Power is added; Cost never is.** The card keeps its own Cost (a
  Symbiote Spider-Man with Galactus merged in gains Galactus's 6 Power but is
  still a 4-Cost card for anything that checks Cost).

## Banish
`status: established` · `aliases: banish, banished` · `verified: player, 2026-11-11`

- Removes a card from the game without destroying or discarding it, so
  "destroyed"/"discarded" counters and triggers don't see it.
- Every Skill is banished after it's played (see Skills).

## Revive, Resurrect and Regenerate
`status: established` · `aliases: revive, resurrect, regenerate, return, comes back, revival` · `verified: player, 2026-11-11`

- All return a card to play, usually at a location. Revive and resurrect
  bring back cards that were destroyed (and, where the text says, discarded);
  regenerate is a card returning itself (Wolverine, X-23).
- **The returning card's On Reveal happens.** Reviving, resurrecting or
  regenerating an On Reveal card is a way to get its effect again (e.g.
  Hela resurrecting discarded cards, Phoenix Force reviving a destroyed one).
- Unconfirmed: whether a returned card's Activate or Objective is available
  again. The player's understanding is that both are once per game, so treat
  a used Activate or completed Objective as spent unless shown otherwise.

## Copy and remove text
`status: established` · `aliases: copy, copies, copy text, remove text, remove abilities, silence, blank`

- "Copy its text" gives a card another card's abilities (Mystique copies the
  last card's Ongoing; Prodigy copies the card in front). Copying an On Reveal
  makes it happen as part of the copier's reveal.
- Astral Projection doesn't let you choose: with several On Reveal cards in
  hand, it copies one at random (verified: player, 2026-11-11).
- A copied On Reveal happens where the copier was played: "here" means the
  location Astral Projection was played at, even though the Skill is banished
  (e.g. copying Arthur Pendragon pulls Excalibur to that location; verified:
  player, 2026-11-11).
- "Remove the text/abilities" blanks a card. A blanked Ongoing card stops
  applying; a blanked card in hand never does its ability.

## Transform
`status: established` · `aliases: transform, transforms, becomes` · `verified: player, 2026-11-11`

- The card becomes a different card (e.g. Polymorph: "Transform your
  lowest-Power character here into one that costs 1 more"). Treat it as the
  new card from then on.

## Replace and destroy locations
`status: established` · `aliases: replace location, destroy location, change location`

- Some cards replace a location with a new random one (Scarlet Witch) or
  destroy locations (Galactus). Cards at a destroyed location are destroyed.

# Interaction principles

## Order of effects
`status: established` · `aliases: timing, resolution order, sequencing, interactions`

- Within a reveal, effects happen in the order cards reveal (see Revealing
  and priority). Ongoing effects apply immediately and keep updating;
  On Reveals happen once at the moment they reveal.
- A card that counts something ("for each…", "if you're winning here")
  checks at the moment it resolves (On Reveal) or continuously (Ongoing).
- Effects that repeat or copy On Reveals (Wong, Odin, Mystique-style copies)
  multiply whatever the On Reveal does, including its downsides.

## Counters and protection
`status: established` · `aliases: counters, tech cards, shutdown, protection`

- Each archetype has natural counters, and creative decks often turn a counter
  into an engine. Examples: Cosmo stops On Reveals at its location; Enchantress
  and Echo remove Ongoing abilities; Leech blanks expensive cards in the
  opponent's hand; Shadow King resets Power; Professor X locks a location;
  Luke Cage protects front-row cards from Power reduction.
- Check the current text in the database before relying on a counter: they
  are among the cards most often changed by patches.
