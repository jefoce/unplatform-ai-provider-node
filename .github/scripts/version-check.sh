#!/usr/bin/env bash
set -euo pipefail

MARKER='<!-- pr-version apply-on-next -->'
MESSAGE='Not merged into releases. Apply these updates on the next version branch, then close this PR.'

fail() {
  echo "::error::$1"
  exit 1
}

is_newer() {
  local candidate="$1"
  local current="$2"
  if [[ "${candidate}" == "${current}" ]]; then
    return 1
  fi
  [[ "$(printf '%s\n%s\n' "${candidate}" "${current}" | sort -V | tail -n 1)" == "${candidate}" ]]
}

if [[ "${PR_AUTHOR}" == "dependabot[bot]" && "${BASE_REF}" == "releases" ]]; then
  if [[ -z "${GH_TOKEN:-}" ]]; then
    fail "GH_TOKEN is required to label a Dependabot PR."
  fi
  body="$(printf '%s\n%s' "${MARKER}" "${MESSAGE}")"
  gh label create apply-on-next --force --repo "${GITHUB_REPOSITORY}" \
    --description 'Apply on the next version branch' --color fbca04
  gh pr edit "${PR_NUMBER}" --repo "${GITHUB_REPOSITORY}" --add-label apply-on-next
  comment_id="$(gh api --paginate \
    "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
    --jq ".[] | select(.body | contains(\"${MARKER}\")) | .id" | head -n 1)"
  if [[ -n "${comment_id}" ]]; then
    gh api --method PATCH \
      "repos/${GITHUB_REPOSITORY}/issues/comments/${comment_id}" \
      -f body="${body}" >/dev/null
  else
    gh api --method POST \
      "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
      -f body="${body}" >/dev/null
  fi
  echo "Dependabot PR into releases: labeled apply-on-next."
  exit 0
fi

semver_re='^[0-9]+\.[0-9]+\.[0-9]+$'

version_pyproject="$(grep -E '^version = "' pyproject.toml | head -n 1 | sed -E 's/^version = "(.*)"$/\1/' || true)"
[[ "${version_pyproject}" =~ ${semver_re} ]] \
  || fail "pyproject.toml version must be X.Y.Z, got '${version_pyproject}'."

version_module="$(grep -E '^__version__ = "' upai_provider/version.py | sed -E 's/^__version__ = "(.*)"$/\1/' || true)"
[[ "${version_module}" =~ ${semver_re} ]] \
  || fail "upai_provider/version.py __version__ must be X.Y.Z, got '${version_module}'."

[[ "${version_module}" == "${version_pyproject}" ]] \
  || fail "Version mismatch: pyproject.toml '${version_pyproject}' and version.py '${version_module}'."

[[ "${TITLE}" == "${version_pyproject}" ]] \
  || fail "PR title must be exactly '${version_pyproject}', got '${TITLE}'."

grep -Eq "^## ${version_pyproject} - [0-9]{4}-[0-9]{2}-[0-9]{2}$" CHANGELOG.md \
  || fail "CHANGELOG.md needs a section '## ${version_pyproject} - YYYY-MM-DD'."
if grep -Eq "^## ${version_pyproject} - unreleased$" CHANGELOG.md; then
  fail "CHANGELOG.md section for ${version_pyproject} still says unreleased."
fi

newest_tag="$(git tag --list 'v*' | sed 's/^v//' | sort -V | tail -n 1)"
if [[ -n "${newest_tag}" ]] && ! is_newer "${version_pyproject}" "${newest_tag}"; then
  fail "Version ${version_pyproject} must be greater than the newest tag v${newest_tag}."
fi

echo "Version ${version_pyproject} is valid."
