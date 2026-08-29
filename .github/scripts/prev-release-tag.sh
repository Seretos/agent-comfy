#!/usr/bin/env bash
# Print the released `agent-comfy--v*` tag that immediately precedes
# <new-tag>, by explicit semver comparison — never by assuming <new-tag> is
# (or is not) already present in `git tag --list`. Prints nothing (and still
# exits 0) when no tag precedes <new-tag> (first release, or first release of
# a new major/minor line). Never blocks a release under normal inputs; exits
# 1 only on a pathological >9999-digit numeric version component, which is
# extremely unlikely from this repo's semver-validated version inputs — the
# semver regex validates format, not digit count, so it doesn't technically
# bound this (see encode_num below).
#
# Usage: prev-release-tag.sh <new-tag>
#   e.g. prev-release-tag.sh agent-comfy--v1.2.3
#
# Requires the repo to have been checked out with full history
# (fetch-depth: 0) so `git tag --list` sees every prior release tag.
#
# The `agent-comfy--v` prefix is a hard-coded constant here, not a runtime
# parameter — this script is specific to the agent-comfy release tag scheme.
set -euo pipefail

NEW_TAG="${1:?usage: prev-release-tag.sh <new-tag>}"

PREFIX='agent-comfy--v'

ONE_ID='(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)'
SEMVER_RE="^${PREFIX}(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(-${ONE_ID}(\\.${ONE_ID})*)?\$"

{
  git tag --list "${PREFIX}*" | grep -E "$SEMVER_RE" || true
  echo "$NEW_TAG"
} | awk -v prefix="$PREFIX" '
  function encode_num(numstr,    stripped) {
    stripped = numstr
    sub(/^0+/, "", stripped)
    if (stripped == "") stripped = "0"
    if (length(stripped) > 9999) {
      print "prev-release-tag.sh: numeric field has " length(stripped) \
        " digits, exceeding the 9999-digit bound the length-prefix " \
        "encoding can represent correctly; refusing to produce a " \
        "possibly-wrong ordering" > "/dev/stderr"
      exit 1
    }
    return sprintf("%04d", length(stripped)) stripped
  }
  BEGIN {
    SEP = sprintf("%c", 31)
  }
  {
    tag = $0
    body = substr(tag, length(prefix) + 1)
    dash = index(body, "-")
    if (dash > 0) {
      core = substr(body, 1, dash - 1)
      prerelease = substr(body, dash + 1)
    } else {
      core = body
      prerelease = ""
    }
    # A single-character fs argument to split() is used as a literal
    # separator, not as an ERE, per POSIX awk semantics (the same rule
    # FS follows) — so this splits on literal dots only, never on "any
    # char". Verified with gawk 5.3 here; the rule is POSIX-mandated
    # awk behavior, not a gawk extension, so mawk/busybox awk on the CI
    # runner honor it too. Do not "fix" this without re-verifying first.
    n = split(core, cf, ".")
    key = ""
    for (i = 1; i <= n; i++) {
      if (i > 1) key = key SEP
      key = key encode_num(cf[i])
    }
    if (prerelease == "") {
      key = key "~"
    } else {
      # Same literal-dot semantics as the split() above — single-char fs,
      # not an ERE wildcard.
      m = split(prerelease, pf, ".")
      for (i = 1; i <= m; i++) {
        key = key SEP
        if (pf[i] ~ /^[0-9]+$/) {
          key = key "0" encode_num(pf[i])
        } else {
          key = key "1" pf[i]
        }
      }
    }
    print key "\t" tag
  }
' | LC_ALL=C sort -u | awk -F'\t' -v new="$NEW_TAG" '
  $2 == new { print prev; found = 1; exit }
  { prev = $2 }
  END { if (!found) exit 0 }
'
