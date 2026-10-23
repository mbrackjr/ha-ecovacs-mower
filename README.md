# pr-restack

Keeps stacked pull-request branches on my fork of
[`nord-/ha-ecovacs-mower`](https://github.com/nord-/ha-ecovacs-mower) rebased
onto upstream `master`, so the next PR in a stack is mergeable as soon as the
one below it is squash-merged — without anyone having to be online.

## How it works

Every hour (and on demand), for each stack in `stacks.toml`:

1. **Cut off what has landed.** A stack branch whose upstream PR is merged is
   removed with `git rebase --onto master <its head>`. This works however many
   commits that PR had and however upstream merged it.
2. **Keep the stack consistent.** A branch that no longer contains the branch
   below it — e.g. review fixes were pushed to the lower PR — is rebased onto
   it.
3. **Rebase onto upstream `master`** with `--update-refs`, which carries every
   branch below the top along. A commit whose change upstream already has as
   a single commit is dropped by the rebase itself.

It pushes **only if** one of those changed something, or GitHub reports one
of the stack's PRs as conflicting. Otherwise nothing is pushed, so an open PR
does not get a force-push every time upstream `master` moves. Before a push,
the tests must pass on every rebased branch. Pushes use `--force-with-lease`
against the SHAs fetched at the start and are `--atomic`: all branches of a
stack or none.

A real conflict, or failing tests, pushes nothing and fails the run; GitHub
then emails me and that stack needs a manual rebase.

Only the branches listed in `stacks.toml` are ever pushed, and only to the
fork. Nothing is ever pushed to upstream.

## Maintaining the stacks

- **New stack:** add a `[[stack]]` with its branches, bottom first, each with
  its upstream PR number once it has one.
- **A PR has landed:** the run summary says so; remove that branch from the
  stack (or the whole stack).
- **A PR carried as one commit** (like #151 here) is *not* listed: the rebase
  drops that commit by itself once the PR is squash-merged.
- **Dry run:** Actions → Restack → *Run workflow* (dry run is ticked by
  default) rebases and tests, but pushes nothing.

## Setup

- Secret `FORK_TOKEN`: a fine-grained personal access token, resource owner
  `mbrackjr`, repository access **only** `mbrackjr/ha-ecovacs-mower`,
  permission *Contents: Read and write*. Renew it before it expires; an
  expired token fails the run, which GitHub emails about.
- The repository's own token only reads this repository and the upstream PR
  states.
