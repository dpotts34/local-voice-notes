#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf 'usage: %s CLEAN_PINNED_CHECKOUT\n' "$0" >&2
    exit 2
fi

checkout=$1
patch_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
expected=9bc876635af36df537d9bc6d3f57ad1b76e4f74a
actual=$(git -C "$checkout" rev-parse --verify HEAD)
if [ "$actual" != "$expected" ]; then
    printf 'wrong upstream revision: expected %s, got %s\n' "$expected" "$actual" >&2
    exit 1
fi
if [ -n "$(git -C "$checkout" status --porcelain --untracked-files=all)" ]; then
    printf 'checkout must be clean before applying the patch\n' >&2
    exit 1
fi

git -C "$checkout" apply --check "$patch_dir/nemotron-asr-long-gpu-transducer.patch"
git -C "$checkout" apply "$patch_dir/nemotron-asr-long-gpu-transducer.patch"
git -C "$checkout" diff --check
changed=$(git -C "$checkout" diff --name-only)
if [ "$changed" != 'src/asr/recognizer.cpp' ]; then
    printf 'unexpected changed paths after patch: %s\n' "$changed" >&2
    exit 1
fi

printf 'Patch applied at %s\n' "$actual"
git -C "$checkout" diff --stat
