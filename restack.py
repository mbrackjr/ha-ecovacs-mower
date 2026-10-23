"""Keep stacked pull-request branches on a fork rebased onto upstream master.

A stack is a list of branches on the fork, bottom first: the first builds on
upstream master, each next one on the previous. Upstream squash-merges PRs, so
when a PR a stack builds on lands, master gets one new commit while the stack
still carries that PR's original commits, and GitHub shows the next PR as
conflicting. This script repairs that, without anyone having to be online:

1. Landed branches are cut off. A stack branch whose upstream PR is merged is
   removed from the stack with `git rebase --onto master <its head>`, which
   works however many commits the PR had and however it was merged.
2. The stack is kept consistent. A branch that no longer contains the branch
   below it (e.g. review fixes were pushed to the lower PR) is rebased onto
   it.
3. The top is rebased onto upstream master with `--update-refs`, which carries
   every branch below it along. A commit whose change upstream already has as
   a single commit (e.g. a PR carried here as one commit, then squash-merged)
   is dropped by the rebase itself.

It pushes only when one of those changed something, or when GitHub reports
one of the stack's PRs as conflicting. Otherwise nothing is pushed, so an open
PR does not get a force-push every time upstream master moves. Before a push,
the test command must pass on every branch that changed. Every push is
`--force-with-lease` against the SHA fetched at the start, and atomic per
stack: all branches or none. A real conflict or a failing test pushes nothing
and fails the run.

Only the branches listed in the config are ever pushed, and only to the fork.
Nothing is ever pushed to upstream.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

WORKDIR = Path(os.environ.get("RESTACK_WORKDIR", "work")).resolve()
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


class Conflict(Exception):
    """A rebase stopped on a conflict that needs a human."""


def run(*args: str, cwd: Path = WORKDIR, check: bool = True) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed:\n{result.stdout}{result.stderr}")
    return result.stdout.strip()


def git(*args: str, check: bool = True) -> str:
    return run("git", *args, check=check)


def is_ancestor(a: str, b: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", a, b], cwd=WORKDIR
    ).returncode == 0


def rebase(*args: str) -> None:
    result = subprocess.run(["git", "rebase", *args], cwd=WORKDIR, text=True, capture_output=True)
    if result.returncode != 0:
        conflicted = git("diff", "--name-only", "--diff-filter=U", check=False)
        git("rebase", "--abort", check=False)
        print(result.stdout, result.stderr)
        raise Conflict(conflicted.replace("\n", ", ") or "(see the log)")


def summary(line: str = "") -> None:
    print(line)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def pr_info(repo: str, number: int) -> dict | None:
    """The upstream PR's state: merged, head SHA, conflicting. None if unknown.

    RESTACK_PR_INFO, a JSON object keyed by PR number, replaces the API for
    local tests.
    """
    if fake := os.environ.get("RESTACK_PR_INFO"):
        return json.loads(fake).get(str(number))
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/pulls/{number}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except Exception as exc:  # noqa: BLE001 - unknown is a valid answer here
        print(f"  could not read PR #{number}: {exc}")
        return None
    return {
        "merged": bool(data.get("merged")),
        "open": data.get("state") == "open",
        "head_sha": data["head"]["sha"],
        # "dirty" is GitHub's word for "has merge conflicts".
        "conflicting": data.get("mergeable_state") == "dirty",
    }


def have_commit(sha: str, pr: int) -> bool:
    def present() -> bool:
        return subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=WORKDIR, capture_output=True
        ).returncode == 0

    if present():
        return True
    # A merged PR's head may be gone from the fork; upstream keeps it.
    git("fetch", "--quiet", "upstream", f"refs/pull/{pr}/head", check=False)
    return present()


def setup(config: dict) -> None:
    fork_url = os.environ.get("FORK_URL") or (
        f"https://x-access-token:{os.environ['FORK_TOKEN']}@github.com/{config['fork']}.git"
    )
    upstream_url = os.environ.get("UPSTREAM_URL") or f"https://github.com/{config['upstream']}.git"
    if not WORKDIR.exists():
        run("git", "clone", "--quiet", "--no-checkout", fork_url, str(WORKDIR), cwd=Path.cwd())
    git("remote", "add", "upstream", upstream_url, check=False)
    git("fetch", "--quiet", "--prune", "origin")
    git("fetch", "--quiet", "upstream", config.get("upstream_branch", "master"))
    git("config", "user.name", config["committer_name"])
    git("config", "user.email", config["committer_email"])


def restack(config: dict, stack: dict, tests_ready: list[bool]) -> bool:
    """Restack one stack. Returns False on a failure that needs a human."""
    base = f"upstream/{config.get('upstream_branch', 'master')}"
    entries: list[dict] = stack["branches"]
    summary(f"### {stack['name']}")

    missing = [e["branch"] for e in entries
               if not git("rev-parse", "--verify", "--quiet", f"origin/{e['branch']}", check=False)]
    if missing:
        summary(f"- ⚠️ not on the fork: {', '.join(missing)}. Remove them from the config.")
        return False

    # 1. Which branches, from the bottom, have landed upstream?
    infos = {e["pr"]: pr_info(config["upstream"], e["pr"]) for e in entries if e.get("pr")}
    landed: list[tuple[dict, str]] = []
    for e in entries:
        info = infos.get(e.get("pr"))
        if not (info and info["merged"]):
            break
        landed.append((e, info["head_sha"]))
    remaining = entries[len(landed):]
    for e, _ in landed:
        summary(f"- ✅ {e['branch']} (#{e['pr']}) has landed. Remove it from the config.")
    if not remaining:
        summary("- ✅ the whole stack has landed. Remove the stack from the config.")
        return True

    branches = [e["branch"] for e in remaining]
    old = {b: git("rev-parse", f"origin/{b}") for b in branches}
    git("checkout", "--quiet", "--force", "--detach", base)
    for b in branches:
        git("branch", "--force", "--no-track", b, old[b])
    reasons: list[str] = []

    try:
        # 2. Each branch must contain the one below it.
        for lower, upper in zip(branches, branches[1:]):
            lower_head, upper_head = git("rev-parse", lower), git("rev-parse", upper)
            if not is_ancestor(lower_head, upper_head):
                fork_point = git("merge-base", lower_head, upper_head)
                rebase("--onto", lower, fork_point, upper)
                reasons.append(f"{upper} restacked onto the updated {lower}")

        # 3. Cut off a landed branch, or rely on the rebase to drop what landed.
        top = branches[-1]
        before = int(git("rev-list", "--count", f"{base}..{top}"))
        git("checkout", "--quiet", "--force", top)
        cut = None
        if landed:
            last, head_sha = landed[-1]
            bottom = git("rev-parse", branches[0])
            if not have_commit(head_sha, last["pr"]):
                summary(f"- ⚠️ cannot find the landed head {head_sha[:7]} of #{last['pr']}; falling back to a plain rebase.")
            elif is_ancestor(head_sha, bottom):
                cut = head_sha
            elif not is_ancestor(base, bottom):
                # The stack has an older version of the landed branch (it never
                # got that PR's last commits): cut where the two part.
                cut = git("merge-base", head_sha, bottom)
            # Otherwise the landed branch was cut off in an earlier run.
        if cut:
            rebase("--update-refs", "--onto", base, cut, top)
            reasons.append(f"cut off the landed {landed[-1][0]['branch']}")
        else:
            rebase("--update-refs", base)
        after = int(git("rev-list", "--count", f"{base}..{top}"))
        if not cut and after < before:
            reasons.append(f"{before - after} commit(s) already upstream dropped")
    except Conflict as conflict:
        summary(f"- ❌ rebase conflicts in: {conflict}. Needs a manual rebase; nothing pushed.")
        return False

    new = {b: git("rev-parse", b) for b in branches}
    conflicting = [e["pr"] for e in remaining if (infos.get(e.get("pr")) or {}).get("conflicting")]
    if conflicting:
        reasons.append(f"upstream reports conflicts on {', '.join(f'#{n}' for n in conflicting)}")
    empty = [b for b in branches if new[b] == git("rev-parse", base)]
    if empty:
        summary(f"- ⚠️ would become empty, so nothing pushed: {', '.join(empty)}. Has its PR landed? Then remove it from the config.")
        return False
    if not reasons:
        summary("- ✅ nothing to do: nothing landed upstream, the stack is consistent, no conflicts reported.")
        return True
    for reason in reasons:
        summary(f"- {reason}")

    changed = [b for b in branches if new[b] != old[b]]
    if command := config.get("test_command"):
        if not tests_ready[0] and (setup_cmd := config.get("test_setup")):
            run("sh", "-c", setup_cmd)
            tests_ready[0] = True
        for b in changed:
            git("checkout", "--quiet", "--force", b)
            result = subprocess.run(["sh", "-c", command], cwd=WORKDIR, text=True, capture_output=True)
            if result.returncode != 0:
                summary(f"- ❌ tests fail on the rebased {b}; nothing pushed.")
                print(result.stdout[-4000:], result.stderr[-4000:])
                return False
            summary(f"- tests pass on the rebased {b}")

    moves = ", ".join(f"{b} {old[b][:7]}→{new[b][:7]}" for b in changed)
    if DRY_RUN:
        summary(f"- 🧪 dry run, would push: {moves}")
        return True
    leases = [f"--force-with-lease=refs/heads/{b}:{old[b]}" for b in changed]
    refspecs = [f"{new[b]}:refs/heads/{b}" for b in changed]
    git("push", "--atomic", *leases, "origin", *refspecs)
    summary(f"- 🚀 pushed: {moves}")
    return True


def main() -> int:
    config = tomllib.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "stacks.toml").read_text())
    setup(config)
    summary(f"## Restack{' (dry run)' if DRY_RUN else ''}")
    ok = True
    tests_ready = [False]
    for stack in config.get("stack", []):
        try:
            ok = restack(config, stack, tests_ready) and ok
        except Exception as exc:  # noqa: BLE001 - report and carry on with the next stack
            summary(f"- ❌ {exc}")
            git("rebase", "--abort", check=False)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
