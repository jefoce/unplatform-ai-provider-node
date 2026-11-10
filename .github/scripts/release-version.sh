#!/usr/bin/env bash
set -euo pipefail

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

semver_re='^[0-9]+\.[0-9]+\.[0-9]+$'

version_pyproject="$(grep -E '^version = "' pyproject.toml | head -n 1 | sed -E 's/^version = "(.*)"$/\1/' || true)"
[[ "${version_pyproject}" =~ ${semver_re} ]] \
  || fail "pyproject.toml version must be X.Y.Z, got '${version_pyproject}'."

version_module="$(grep -E '^__version__ = "' upai_provider/version.py | sed -E 's/^__version__ = "(.*)"$/\1/' || true)"
[[ "${version_module}" =~ ${semver_re} ]] \
  || fail "upai_provider/version.py __version__ must be X.Y.Z, got '${version_module}'."

[[ "${version_module}" == "${version_pyproject}" ]] \
  || fail "Version mismatch: pyproject.toml '${version_pyproject}' and version.py '${version_module}'."

version="${version_pyproject}"

if grep -Eq "^## ${version} - unreleased$" CHANGELOG.md; then
  echo "release=false" >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
  echo "::notice::Version ${version} is unreleased; skipping tag and publish."
  exit 0
fi

grep -Eq "^## ${version} - [0-9]{4}-[0-9]{2}-[0-9]{2}$" CHANGELOG.md \
  || fail "CHANGELOG.md needs a section '## ${version} - YYYY-MM-DD'."

tag="v${version}"
tag_commit="$(git rev-parse -q --verify "refs/tags/${tag}" || true)"
head_commit="$(git rev-parse HEAD)"
if [[ -n "${tag_commit}" ]]; then
  [[ "${tag_commit}" == "${head_commit}" ]] \
    || fail "Tag ${tag} exists at ${tag_commit}, not at HEAD ${head_commit}."
  echo "::notice::Tag ${tag} already exists at HEAD; re-running the release."
else
  newest_tag="$(git tag --list 'v*' | sed 's/^v//' | sort -V | tail -n 1)"
  if [[ -n "${newest_tag}" ]] && ! is_newer "${version}" "${newest_tag}"; then
    fail "Version ${version} must be greater than the newest tag v${newest_tag}."
  fi
fi

awk -v header="## ${version} " '
  index($0, header) == 1 {in_section = 1; next}
  in_section && /^## / {exit}
  in_section {print}
' CHANGELOG.md > release-notes.md
[[ -s release-notes.md ]] || fail "CHANGELOG.md section for ${version} is empty."

{
  echo "release=true"
  echo "version=${version}"
  echo "tag=${tag}"
} >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"

echo "Release ${version} ready."
