---
status: accepted
date: 2026-10-20
decision-makers: Marcel Bruckner
---

# State law from the official state portals, one data repo per state

## Context and Problem Statement

Gesetze für KI served only federal law, mirrored from gesetze-im-internet.de, which publishes it as open data.
Users asked for state law (Landesrecht). There is no open-data source for it: each state has its own portal,
and the only aggregator (landesrecht.online) is a private publisher's database with no licence. Where should
state texts come from, which states can be mirrored at all, and how should they be stored next to the federal
repo?

## Decision Drivers

* Legally safe: only mirror what a portal does not forbid (robots.txt, terms of use, database rights).
* Polite: honour crawl delays; never let one source bypass them.
* Reversible per state: if a state objects, its data and history must be removable without touching the rest.
* Missing states must be visible, not silently absent.

## Considered Options

* Mirror landesrecht.online (all 16 states, one source)
* Mirror the official portals, all states in one data repo (`land/<code>/` in `gesetze`)
* Mirror the official portals, one data repo per state (`landesrecht-<code>`)

## Decision Outcome

Chosen option: "official portals, one data repo per state". landesrecht.online is a private database without a
licence (§ 87a UrhG), so it is out. Of the 16 official portals, ten (juris) forbid generic crawlers in
robots.txt and Niedersachsen's operator reserves use, so only Bayern (explicit licence), Sachsen, NRW,
Brandenburg (no licence, nothing forbidden) and Bremen (CC BY-NC-ND 3.0) are mirrored. One repo per state
keeps each licence separate, keeps the federal history free of partial state passes, avoids push conflicts
between nightly jobs, and lets a state be removed by deleting one repo. The eleven other states get a repo
with a README explaining why they are missing.

### Consequences

* Good, because federal data, workflow and Markdown format stay untouched.
* Good, because each state's sync runs in its own Action, so Brandenburg's slow crawl (20 s delay, no change
  signal, about two nights per pass) delays nobody.
* Bad, because the server clones and updates six repos instead of one, and the history tools must know which
  repo a law lives in (`server.clone_for`).
* Bad, because each portal needs its own parser (`app/sources/`), which breaks when a portal changes its
  layout. The runner refuses to write texts without norms and refuses mass deletions to contain that.

## More Information

Issue #9. The sync's command line (`sync.py --land <code>`) is shared with the state repos' workflows; a change
must be made there too. `.sync/state.json` in each state repo is read by `store.build` to decide whether a
state is complete and searchable.
