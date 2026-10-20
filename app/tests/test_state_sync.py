import datetime
import json
import sys

import httpx
import pytest

import sources
import state_sync
import sync

D = datetime.date(2026, 10, 20)


def law(title: str) -> str:
    """A law file with a title line and one norm (the runner refuses files without any)."""
    return f"# {title}\n\n<!-- norm id=\"par1\" -->\n## § 1\n\nText.\n"


class FakeSource:
    """Serves laws from dicts; every list/fetch is a real request through the given client."""

    code = "BY"
    crawl_delay = 0.0
    workers = 1

    def __init__(self, n=10, min_entries=5):
        self.min_entries = min_entries
        self.lastmod = {f"by-law{i:02d}": "2026-01-01" for i in range(n)}
        self.texts = {slug: law(slug) for slug in self.lastmod}
        self.future: dict[str, tuple[datetime.date, str]] = {}  # slug -> (start date, new text)
        # slug -> (start date, text): the portal only has a text that starts later (NotYetInForce before then)
        self.pending: dict[str, tuple[datetime.date, str]] = {}
        self.fetches = 0
        self.requests = 0
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request):
        self.requests += 1
        return httpx.Response(200, text="ok")

    def list_laws(self, client):
        client.get("https://fake.example/list")
        return [state_sync.Entry(slug, f"https://fake.example/{slug}", lm) for slug, lm in self.lastmod.items()]

    def fetch(self, client, entry, today):
        client.get(entry.url)
        self.fetches += 1
        if entry.slug in self.pending:
            start, new = self.pending[entry.slug]
            if today < start:
                raise state_sync.NotYetInForce(start.isoformat())
            self.texts[entry.slug] = new
        text, nvf = self.texts[entry.slug], None
        if entry.slug in self.future:
            start, new = self.future[entry.slug]
            if today >= start:
                text = new
            else:
                nvf = start.isoformat()
        front = {"slug": entry.slug, "abkuerzung": entry.slug.upper(), "titel": "Gesetz", "stand": "x"}
        return state_sync.Fetched(markdown=text, front=front, next_version_from=nvf)


class FakeClock:
    """Advances by step_seconds on every call."""

    def __init__(self, step_seconds=0):
        self.t = 0.0
        self.step = step_seconds

    def __call__(self):
        t = self.t
        self.t += self.step
        return t


def noop(_):
    pass


def run(tmp_path, src, only=None, max_minutes=330, today=D, clock=None, sleep=noop):
    return state_sync.run(tmp_path, src, only, max_minutes=max_minutes, today=today,
                          clock=clock or FakeClock(), sleep=sleep, transport=src.transport)


def load_state(out):
    return json.loads((out / ".sync" / "state.json").read_text())


def commit_msg(out):
    return (out / ".sync" / "commit-message.txt").read_text(encoding="utf-8")


def files(out):
    return sorted(p.stem for p in out.glob("*/*.md"))


def test_state_law_path_shards_by_id():
    out = state_sync.Path("/d")
    assert state_sync.state_law_path(out, "by-baybo") == out / "ba" / "by-baybo.md"
    # Numeric ids (Sachsen) are sharded by their first two digits, not all into "0-9".
    assert state_sync.state_law_path(out, "sn-20111") == out / "20" / "sn-20111.md"
    assert state_sync.state_law_path(out, "sn-3975") == out / "39" / "sn-3975.md"
    assert state_sync.state_law_path(out, "sn-7") == out / "0-9" / "sn-7.md"


def test_first_pass_resumes_across_runs(tmp_path):
    src = FakeSource(n=10, min_entries=5)
    clock = FakeClock(step_seconds=60)  # each fetch "takes" a minute
    assert state_sync.run(tmp_path, src, None, max_minutes=4, today=D, clock=clock, sleep=noop,
                          transport=src.transport) == 0
    st = load_state(tmp_path)
    assert not st["complete"] and 0 < len(st["pass_done"]) < 10
    assert "Abgleich läuft noch:" in commit_msg(tmp_path)
    assert commit_msg(tmp_path).splitlines()[0].startswith("Bayern Stand 2026-10-20: 0 geändert, ")
    runs = 0
    while not load_state(tmp_path)["complete"]:
        runs += 1
        assert runs < 10
        run(tmp_path, src, max_minutes=4, clock=FakeClock(60))
    assert len(list(tmp_path.glob("*/*.md"))) == 10
    st = load_state(tmp_path)
    assert st["pass_done"] == [] and len(st["laws"]) == 10
    assert "Abgleich läuft noch:" not in commit_msg(tmp_path)


def test_complete_stays_true_during_later_partial_pass(tmp_path):
    src = FakeSource()
    assert run(tmp_path, src) == 0
    assert load_state(tmp_path)["complete"]
    src.lastmod = {slug: "2026-02-02" for slug in src.lastmod}
    assert run(tmp_path, src, max_minutes=4, clock=FakeClock(60)) == 0
    st = load_state(tmp_path)
    assert st["complete"] and 0 < len(st["pass_done"]) < 10


def test_short_listing_refuses_and_deletes_nothing(tmp_path):
    src = FakeSource(n=10, min_entries=5)
    assert run(tmp_path, src) == 0
    before = (tmp_path / ".sync" / "state.json").read_bytes()
    src.lastmod = dict(list(src.lastmod.items())[:2])
    assert run(tmp_path, src) == 2
    assert len(files(tmp_path)) == 10
    # The state is untouched and there is no commit message, not even the last run's.
    assert (tmp_path / ".sync" / "state.json").read_bytes() == before
    assert [p.name for p in (tmp_path / ".sync").iterdir()] == ["state.json"]


def test_short_listing_on_first_run_writes_nothing(tmp_path):
    src = FakeSource(n=2, min_entries=5)
    assert run(tmp_path, src) == 2
    assert list(tmp_path.iterdir()) == []


def test_removed_law_deleted_after_full_pass(tmp_path):
    src = FakeSource(n=10, min_entries=5)
    assert run(tmp_path, src) == 0
    del src.lastmod["by-law03"]
    assert run(tmp_path, src) == 0
    assert "by-law03" not in files(tmp_path) and len(files(tmp_path)) == 9
    assert "- entfernt: by-law03" in commit_msg(tmp_path)
    assert "by-law03" not in load_state(tmp_path)["laws"]


def test_only_never_deletes_and_keeps_pass_state(tmp_path):
    src = FakeSource(n=10, min_entries=5)
    assert run(tmp_path, src, max_minutes=4, clock=FakeClock(60)) == 0
    st = load_state(tmp_path)
    del src.lastmod["by-law09"]
    src.texts["by-law08"] = law("neu")
    src.fetches = 0
    assert run(tmp_path, src, only=["by-law08"]) == 0
    assert src.fetches == 1
    after = load_state(tmp_path)
    assert after["complete"] == st["complete"] and after["pass_done"] == st["pass_done"]
    path = state_sync.state_law_path(tmp_path, "by-law08")
    assert path.read_text() == law("neu")


def test_new_and_changed_laws_in_commit_message(tmp_path):
    src = FakeSource(n=10)
    assert run(tmp_path, src) == 0
    assert "- neu: BY-LAW00 (Gesetz)" in commit_msg(tmp_path)
    src.lastmod["by-law01"] = "2026-03-03"
    src.texts["by-law01"] = law("geändert")
    assert run(tmp_path, src) == 0
    msg = commit_msg(tmp_path)
    assert msg.splitlines()[0] == "Bayern Stand 2026-10-20: 1 geändert, 0 neu, 0 entfernt"
    assert "- BY-LAW01: x" in msg


def test_unchanged_lastmod_is_not_refetched(tmp_path):
    src = FakeSource()
    assert run(tmp_path, src) == 0
    src.fetches = 0
    assert run(tmp_path, src) == 0
    assert src.fetches == 0
    assert load_state(tmp_path)["complete"]


def test_missing_file_is_refetched(tmp_path):
    src = FakeSource()
    assert run(tmp_path, src) == 0
    state_sync.state_law_path(tmp_path, "by-law04").unlink()
    src.fetches = 0
    assert run(tmp_path, src) == 0
    assert src.fetches == 1 and "by-law04" in files(tmp_path)


def test_future_version_taken_over_on_start_date(tmp_path):
    src = FakeSource()
    src.future["by-law02"] = (D + datetime.timedelta(days=1), law("neue Fassung"))
    assert run(tmp_path, src) == 0
    path = state_sync.state_law_path(tmp_path, "by-law02")
    assert path.read_text() == src.texts["by-law02"]
    assert load_state(tmp_path)["laws"]["by-law02"]["next_version_from"] == "2026-10-21"
    src.fetches = 0
    assert run(tmp_path, src, today=D) == 0
    assert src.fetches == 0
    assert run(tmp_path, src, today=D + datetime.timedelta(days=1)) == 0
    assert src.fetches == 1
    assert path.read_text() == law("neue Fassung")
    assert load_state(tmp_path)["laws"]["by-law02"]["next_version_from"] is None


def test_text_not_yet_in_force_keeps_the_old_file_and_is_no_failure(tmp_path):
    src = FakeSource()
    assert run(tmp_path, src) == 0
    path = state_sync.state_law_path(tmp_path, "by-law03")
    old = path.read_text()
    start = D + datetime.timedelta(days=3)
    src.pending["by-law03"] = (start, law("ab dem Stichtag"))
    src.lastmod["by-law03"] = "2026-10-23"  # the listing already shows the coming version
    assert run(tmp_path, src) == 0
    st = load_state(tmp_path)
    assert st["complete"] and st["pass_failed"] == []
    assert st["laws"]["by-law03"]["next_version_from"] == start.isoformat()
    assert path.read_text() == old
    assert "Nicht abrufbar" not in commit_msg(tmp_path)
    # not asked again before the start date, although lastmod changed
    src.fetches = 0
    assert run(tmp_path, src, today=D + datetime.timedelta(days=1)) == 0
    assert src.fetches == 0 and path.read_text() == old
    # taken over on the start date
    assert run(tmp_path, src, today=start) == 0
    assert src.fetches == 1 and path.read_text() == law("ab dem Stichtag")
    assert load_state(tmp_path)["laws"]["by-law03"]["next_version_from"] is None


def test_new_law_not_yet_in_force_appears_on_its_start_date(tmp_path):
    src = FakeSource()
    start = D + datetime.timedelta(days=2)
    src.lastmod["by-law99"] = start.isoformat()
    src.pending["by-law99"] = (start, law("neues Gesetz"))
    assert run(tmp_path, src) == 0
    path = state_sync.state_law_path(tmp_path, "by-law99")
    st = load_state(tmp_path)
    assert not path.exists() and st["complete"] and st["pass_failed"] == []
    assert st["laws"]["by-law99"]["next_version_from"] == start.isoformat()
    src.fetches = 0
    assert run(tmp_path, src, today=D + datetime.timedelta(days=1)) == 0
    assert src.fetches == 0 and not path.exists()  # a missing file alone does not trigger a refetch
    assert run(tmp_path, src, today=start) == 0
    assert path.read_text() == law("neues Gesetz")
    assert "- neu: BY-LAW99" in commit_msg(tmp_path)


def test_crawl_delay_sleeps_between_requests(tmp_path):
    src = FakeSource()
    src.crawl_delay = 20
    sleeps = []
    assert run(tmp_path, src, sleep=sleeps.append) == 0
    assert src.requests == 11  # listing + 10 laws
    assert len(sleeps) == src.requests - 1
    assert all(s >= 20 for s in sleeps)


def test_parallel_workers_need_no_crawl_delay(tmp_path):
    src = FakeSource()
    src.crawl_delay, src.workers = 20, 2
    with pytest.raises(ValueError):
        run(tmp_path, src)


def test_failing_law_does_not_block_the_pass(tmp_path):
    src = FakeSource()
    assert run(tmp_path, src) == 0  # first pass: every file exists
    old = state_sync.state_law_path(tmp_path, "by-law05").read_text()
    src.lastmod = {slug: "2026-05-05" for slug in src.lastmod}
    real = src.fetch

    def flaky(client, entry, today):
        if entry.slug == "by-law05":
            raise RuntimeError("boom")
        return real(client, entry, today)

    src.fetch = flaky
    assert run(tmp_path, src) == 0
    st = load_state(tmp_path)
    assert st["complete"] and st["pass_done"] == [] and st["pass_failed"] == []
    assert state_sync.state_law_path(tmp_path, "by-law05").read_text() == old
    assert "Nicht abrufbar (1): by-law05" in commit_msg(tmp_path)
    assert "Abgleich läuft noch" not in commit_msg(tmp_path)
    # the next pass tries it again
    src.fetch = real
    src.fetches = 0
    assert run(tmp_path, src) == 0
    assert src.fetches == 1


def test_failed_law_not_retried_within_a_pass(tmp_path):
    src = FakeSource()
    real = src.fetch
    tried = []

    def flaky(client, entry, today):
        tried.append(entry.slug)
        if entry.slug == "by-law00":
            raise RuntimeError("boom")
        return real(client, entry, today)

    src.fetch = flaky
    assert run(tmp_path, src, max_minutes=4, clock=FakeClock(60)) == 0
    st = load_state(tmp_path)
    assert st["pass_failed"] == ["by-law00"] and not st["complete"]
    tried.clear()
    while not load_state(tmp_path)["complete"]:
        assert run(tmp_path, src, max_minutes=4, clock=FakeClock(60)) == 0
    assert "by-law00" not in tried


def test_too_many_failures_in_a_pass_keep_complete_false(tmp_path):
    src = FakeSource(n=12)

    def broken(client, entry, today):
        raise RuntimeError("boom")

    src.fetch = broken
    run(tmp_path, src)
    st = load_state(tmp_path)
    assert not st["complete"] and st["pass_done"] == [] and st["pass_failed"] == []


def test_interrupted_run_keeps_progress(tmp_path):
    src = FakeSource(n=40)
    real = src.fetch

    def interrupted(client, entry, today):
        if src.fetches == 30:
            raise KeyboardInterrupt
        return real(client, entry, today)

    src.fetch = interrupted
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, src)
    st = load_state(tmp_path)
    assert len(st["pass_done"]) == 30 and len(st["laws"]) == 30
    assert src.fetches == 30


def test_many_failures_exit_1(tmp_path):
    src = FakeSource(n=12)

    def broken(client, entry, today):
        raise RuntimeError("boom")

    src.fetch = broken
    assert run(tmp_path, src) == 1


def test_not_a_law_is_skipped_and_not_refetched(tmp_path):
    src = FakeSource()
    real = src.fetch
    src.fetch = lambda c, e, t: None if e.slug == "by-law07" else real(c, e, t)
    assert run(tmp_path, src) == 0
    assert "by-law07" not in files(tmp_path) and load_state(tmp_path)["complete"]
    calls = []
    src.fetch = lambda c, e, t: calls.append(e.slug)
    assert run(tmp_path, src) == 0
    assert calls == []


def test_federal_cli_unchanged(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(sync, "run", lambda *a: calls.append(a) or 0)
    monkeypatch.setattr(state_sync, "run", lambda *a, **k: pytest.fail("state sync called"))
    monkeypatch.setattr(sys, "argv", ["sync.py", "--out", str(tmp_path), "--only", "estg", "--workers", "3"])
    with pytest.raises(SystemExit) as exc:
        sync.main()
    assert exc.value.code == 0
    assert calls == [(tmp_path, ["estg"], 3)]


def test_cli_land_dispatches_to_state_sync(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(sync, "run", lambda *a: pytest.fail("federal sync called"))
    monkeypatch.setattr(sources, "SOURCES", {"by": FakeSource})
    monkeypatch.setattr(state_sync, "run", lambda *a, **k: calls.append((a, k)) or 0)
    monkeypatch.setattr(sys, "argv", ["sync.py", "--out", str(tmp_path), "--land", "BY", "--max-minutes", "10"])
    with pytest.raises(SystemExit) as exc:
        sync.main()
    assert exc.value.code == 0
    (args, _), = calls
    assert args[0] == tmp_path and isinstance(args[1], FakeSource) and args[2] is None and args[3] == 10


def test_cli_unknown_land_exits_2(monkeypatch, tmp_path):
    monkeypatch.setattr(sources, "SOURCES", {})
    monkeypatch.setattr(sys, "argv", ["sync.py", "--out", str(tmp_path), "--land", "xx"])
    with pytest.raises(SystemExit) as exc:
        sync.main()
    assert exc.value.code == 2


class CachingSource(FakeSource):
    """Keeps something in the runner's per-source cache: the slugs it has listed so far."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.cache: dict = {}
        self.seen_cache: dict | None = None
        self.interrupt = False

    def list_laws(self, client):
        self.seen_cache = dict(self.cache)
        for slug in self.lastmod:
            self.cache[slug] = "known"
        return super().list_laws(client)

    def fetch(self, client, entry, today):
        if self.interrupt:
            raise KeyboardInterrupt
        return super().fetch(client, entry, today)


def test_cache_is_kept_in_the_state_and_handed_back(tmp_path):
    src = CachingSource(n=3, min_entries=1)
    assert run(tmp_path, src) == 0
    assert src.seen_cache == {}
    assert load_state(tmp_path)["cache"] == {f"by-law{i:02d}": "known" for i in range(3)}
    again = CachingSource(n=3, min_entries=1)
    run(tmp_path, again)
    assert again.seen_cache == {f"by-law{i:02d}": "known" for i in range(3)}


def test_cache_is_saved_when_the_run_is_interrupted(tmp_path):
    src = CachingSource(n=3, min_entries=1)
    src.interrupt = True
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, src)
    assert load_state(tmp_path)["cache"] == {f"by-law{i:02d}": "known" for i in range(3)}


def test_a_source_without_a_cache_is_left_alone(tmp_path):
    src = FakeSource(n=3, min_entries=1)
    run(tmp_path, src)
    assert not hasattr(src, "cache")
    assert load_state(tmp_path)["cache"] == {}


def test_cache_is_saved_when_the_listing_breaks_off(tmp_path):
    class Breaking(CachingSource):
        def list_laws(self, client):
            self.cache["half"] = "done"
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, Breaking(n=3, min_entries=1))
    assert load_state(tmp_path)["cache"] == {"half": "done"}


def test_a_text_without_any_norm_is_a_failure_and_keeps_the_old_file(tmp_path):
    # A changed page template must not wipe the texts: a file without a single norm is refused.
    src = FakeSource(min_entries=1)
    assert run(tmp_path, src) == 0
    path = state_sync.state_law_path(tmp_path, "by-law04")
    old = path.read_text()
    src.lastmod["by-law04"] = "2026-05-05"
    src.texts["by-law04"] = "# by-law04\n\nNur noch Navigation.\n"
    assert run(tmp_path, src) == 0
    assert path.read_text() == old
    assert "Nicht abrufbar (1): by-law04" in commit_msg(tmp_path)


def test_cache_is_saved_sorted(tmp_path):
    class Unsorted(CachingSource):
        def list_laws(self, client):
            self.cache.update({"z": "1", "a": "2"})
            return super().list_laws(client)

    run(tmp_path, Unsorted(n=3, min_entries=1))
    keys = list(load_state(tmp_path)["cache"])
    assert keys == sorted(keys)


def test_a_stale_commit_message_is_removed_when_the_listing_is_refused(tmp_path):
    src = FakeSource(n=10, min_entries=5)
    assert run(tmp_path, src) == 0
    src.lastmod = dict(list(src.lastmod.items())[:2])
    assert run(tmp_path, src) == 2
    assert not (tmp_path / ".sync" / "commit-message.txt").exists()


def test_a_listing_that_breaks_off_writes_no_commit_message(tmp_path):
    src = FakeSource()
    assert run(tmp_path, src) == 0

    def broken(client):
        raise RuntimeError("listing down")

    src.list_laws = broken
    with pytest.raises(RuntimeError):
        run(tmp_path, src)
    assert not (tmp_path / ".sync" / "commit-message.txt").exists()


def test_an_interrupted_run_writes_a_commit_message_for_its_progress(tmp_path):
    src = FakeSource(n=40)
    assert run(tmp_path, src) == 0
    src.lastmod = {slug: "2026-05-05" for slug in src.lastmod}
    for slug in ("by-law00", "by-law01"):
        src.texts[slug] = law(f"{slug} geändert")
    real = src.fetch

    def interrupted(client, entry, today):
        if entry.slug == "by-law03":
            raise KeyboardInterrupt
        return real(client, entry, today)

    src.fetch = interrupted
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, src)
    msg = commit_msg(tmp_path)
    assert msg.splitlines()[0] == "Bayern Stand 2026-10-20: 2 geändert, 0 neu, 0 entfernt"
    assert "- BY-LAW00: x" in msg and "- BY-LAW01: x" in msg
    assert msg.rstrip().endswith("Abgleich abgebrochen, Fortschritt gesichert")


def test_a_pass_that_would_delete_too_many_files_deletes_nothing(tmp_path, caplog):
    src = FakeSource(n=30, min_entries=5)
    assert run(tmp_path, src) == 0
    for i in range(11):  # more than _failure_limit(19) == 10
        del src.lastmod[f"by-law{i:02d}"]
    assert run(tmp_path, src) == 1
    assert len(files(tmp_path)) == 30
    assert any(r.levelname == "ERROR" for r in caplog.records)
    assert "entfernt:" not in commit_msg(tmp_path)
    # Up to the limit, laws that left the listing are deleted as before.
    src2 = FakeSource(n=30, min_entries=5)
    out2 = tmp_path / "two"
    assert run(out2, src2) == 0
    for i in range(10):
        del src2.lastmod[f"by-law{i:02d}"]
    assert run(out2, src2) == 0
    assert len(files(out2)) == 20


def test_files_in_dot_directories_are_never_deleted(tmp_path):
    src = FakeSource()
    assert run(tmp_path, src) == 0
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "pull_request_template.md").write_text("Hinweis\n")
    (tmp_path / ".sync" / "notes.md").write_text("x\n")
    assert run(tmp_path, src) == 0
    assert (tmp_path / ".github" / "pull_request_template.md").exists()
    assert (tmp_path / ".sync" / "notes.md").exists()


def test_the_client_retries_once_after_a_server_error_through_the_throttle(tmp_path):
    src = FakeSource(n=1, min_entries=1)
    src.crawl_delay = 20
    responses = iter([httpx.Response(503), httpx.Response(200, text="ok")])
    src.transport = httpx.MockTransport(lambda r: next(responses, httpx.Response(200, text="ok")))
    sleeps = []
    assert run(tmp_path, src, sleep=sleeps.append) == 0
    # listing: 503, backoff, throttled retry; then the law, throttled
    assert sleeps == [state_sync.RETRY_DELAY, 20, 20]


def test_the_client_retries_a_transport_error_once_and_not_a_404(tmp_path):
    calls = []

    def handle(request):
        calls.append(request.url.path)
        if request.url.path == "/down":
            raise httpx.ConnectError("refused")
        if request.url.path == "/flaky" and calls.count("/flaky") == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(404 if request.url.path == "/missing" else 200, text="ok")

    src = FakeSource()
    with state_sync._client(src, noop, httpx.MockTransport(handle)) as client:
        assert client.get("https://fake.example/flaky").text == "ok"
        assert client.get("https://fake.example/missing").status_code == 404
        with pytest.raises(httpx.ConnectError):
            client.get("https://fake.example/down")
    assert calls == ["/flaky", "/flaky", "/missing", "/down", "/down"]
