"""deploy.sh publishes ONLY to the cinema stack: its own bucket and its own distribution. The elyoxe.com
distribution (E2QY4WECG1P5WO) and the shared tools bucket are behind a `--delete` sync away from
losing /tools, /quran or the studio site, so no command in deploy.sh may name them."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUCKET = "elyoxe-cinema-574771023173"
FORBIDDEN = ("E2QY4WECG1P5WO", "elyoxe-tools", "elyoxe-site", "s3://$BUCKET/cinema", "elyoxe.com/cinema")


def _code_lines():
    """deploy.sh as commands: comments dropped (the header may explain what it does NOT touch),
    backslash continuations joined so a multi-line `aws s3 sync` is one entry."""
    src = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
    out, cur = [], ""
    for line in src.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = re.sub(r"\s+#\s.*$", "", s)
        cur += (" " if cur else "") + s.rstrip("\\").rstrip()
        if not s.endswith("\\"):
            out.append(cur); cur = ""
    return out


def test_no_command_names_the_production_distribution_or_tools_bucket():
    for line in _code_lines():
        for bad in FORBIDDEN:
            assert bad not in line, f"deploy.sh references {bad!r}: {line.strip()}"


def test_bucket_and_stack_are_the_cinema_ones():
    code = "\n".join(_code_lines())
    assert f"BUCKET={BUCKET}" in code
    assert re.search(r"\bSTACK=elyoxe-cinema\b", code)
    assert 'DEST="s3://$BUCKET/"' in code
    assert "SITE=https://cinema.elyoxe.com" in code


FAST = 'fast(){ shift 2; "$(command -v python3 || command -v python)" "$(cygpath -m "$HOME" 2>/dev/null || echo "$HOME")/workspace/tools/s3fast.py" "$@" || aws s3 "$@"; }'


def test_every_s3_write_goes_to_the_cinema_bucket_only():
    code = _code_lines()
    # 2026-10-08: every pass goes through the fast uploader (~/workspace/tools/s3fast.py, same arguments; the CLI if it fails),
    # and the helper passes its arguments through untouched
    assert FAST in code, "the fast() helper changed: check it still passes the arguments through unchanged"
    s3 = [l for l in code if re.search(r"\baws s3(api)? ", l) and l != FAST]
    assert len(s3) >= 3, "expected the sync passes"
    for l in s3:
        assert re.search(r"^fast aws s3 sync ", l), f"only `fast aws s3 sync` is allowed: {l.strip()}"
        targets = re.findall(r"(s3://\S+|\"\$DEST\")", l)
        assert targets == ['"$DEST"'], f"sync target must be $DEST: {l.strip()}"
    # no other s3:// literal anywhere
    for l in _code_lines():
        for uri in re.findall(r"s3://[^\s\"']+", l):
            assert uri == "s3://$BUCKET/", f"unexpected S3 URI {uri}"


def test_invalidation_uses_the_cinema_stack_distribution():
    code = _code_lines()
    inv = [l for l in code if "create-invalidation" in l]
    assert inv and all('--distribution-id "$DIST"' in l for l in inv)
    assert any("DIST=$(out_of DistributionId)" in l for l in code)
    assert not any(re.search(r"\bDIST=E", l) for l in code), "distribution id must come from the cinema stack"


def test_tools_preview_dir_is_never_uploaded():
    code = _code_lines()
    assert any('NEVER=(--exclude "tools/*" --exclude "next/*")' in l for l in code)   # /next/: the redesign preview
    for l in code:
        if "aws s3 sync" in l and '--include "data/*"' not in l:
            assert '"${NEVER[@]}"' in l, l


def test_posters_are_never_deleted_by_a_sync():
    """posters/* is uploaded by `posters.py --upload`, not built into out/, so a `--delete` sync that
    does not exclude it would wipe every poster. The exclusion must come AFTER any --include (the
    last matching filter wins in `aws s3 sync`)."""
    code = _code_lines()
    assert any(l.startswith("KEEP=(") and '--exclude "posters/*"' in l for l in code)
    syncs = [l for l in code if "aws s3 sync" in l]
    assert syncs
    for l in syncs:
        if "--delete" not in l:
            continue
        assert '"${KEEP[@]}"' in l, f"--delete pass without the posters exclusion: {l.strip()}"
        incs = [m.start() for m in re.finditer(r"--include ", l)]
        if incs:
            assert l.index('"${KEEP[@]}"') > max(incs), f"posters exclusion must follow the includes: {l.strip()}"


def test_run_uploads_new_posters_before_it_deploys():
    """deploy.sh never uploads posters/ (it keeps them out of every --delete pass), so the scheduled run
    must: a film first seen on the Fold would otherwise name a /posters/ file the bucket does not have."""
    src = open(os.path.join(ROOT, "run.sh"), encoding="utf-8").read()
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    up, dep = code.find("posters.py --upload"), code.find("./deploy.sh")
    assert up != -1 and dep != -1 and up < dep


def test_state_is_never_deleted_by_a_sync():
    """state/price_history.jsonl is written by the refresh step (steps/history.py), never built into out/:
    every `--delete` pass must keep it, or each deploy erases the price history's bucket copy."""
    code = _code_lines()
    keep = next(l for l in code if l.startswith("KEEP=("))
    assert '--exclude "state/*"' in keep and '--exclude "posters/*"' in keep
    for l in code:
        if "aws s3 sync" in l and "--delete" in l:
            assert '"${KEEP[@]}"' in l, l
