# Selected native patch

This directory intentionally stages one sanitized source patch, not the captured deployment patch set. It contains no upstream checkout, submodule, model, binary, build output, benchmark, or machine-specific evidence.

## Selection and provenance

| Patch | Upstream repository | Exact base revision | Purpose |
| --- | --- | --- | --- |
| `nemotron-asr-long-gpu-transducer.patch` | [NVIDIA/NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp) | `9bc876635af36df537d9bc6d3f57ad1b76e4f74a` | For supported non-CTC transducer models, route GPU offline requests longer than 10 seconds through the existing cache-streaming runner. |

The patch is based on the captured change in the private source repository. Its added wording and local constant name were normalized; executable logic and the 10-second threshold are unchanged. This selected patch does not include the separate GGML or Qwen3-TTS patches.

Upstream `LICENSE`, `NOTICE`, and `THIRD_PARTY_NOTICES.md` are copied verbatim from the pinned revision under `licenses/`. Only recognizer source context in the patch is included, not a full upstream checkout or submodules. The patch adds a prominent modification notice immediately after the original copyright/license header; both upstream header lines remain unchanged. The third-party notice file summarizes dependencies; it does not replace checking the applicable dependency notices when building or redistributing combined upstream material.

## Apply and verify

Prerequisites for this check: Git and HTTPS access to the upstream repository. Start with a fresh disposable clone at the exact revision; the checker refuses another revision or a dirty checkout and applies the patch at the repository root. It requires no submodules for patch application.

From the release-preparation root:

```sh
work=$(mktemp -d)
git clone --filter=blob:none --no-checkout https://github.com/NVIDIA/NeMo-Speech.cpp.git "$work/NeMo-Speech.cpp"
git -C "$work/NeMo-Speech.cpp" fetch --depth=1 origin 9bc876635af36df537d9bc6d3f57ad1b76e4f74a
git -C "$work/NeMo-Speech.cpp" checkout --detach 9bc876635af36df537d9bc6d3f57ad1b76e4f74a
./patches/verify-application.sh "$work/NeMo-Speech.cpp"
```

The script runs `git apply --check`, applies the patch, checks whitespace, and requires exactly `src/asr/recognizer.cpp` to change. Use a fresh checkout for each run because a successful run modifies that file.

## Limits and release gate

- This patch only applies to the pinned NeMo-Speech.cpp revision without adaptation. The 10-second threshold is a fixed behavior in this patch, not a general hardware recommendation.
- The additional route is gated on a GPU backend, a non-CTC model, a usable sample rate, and the model's existing cache-streaming support. This does not establish support for any particular historic GPU, CUDA/ROCm version, driver, or model.
- The check proves patch application only. It is not a fresh build, GPU build, inference, performance, or stability test. Building and running require the upstream project's own prerequisites and compatible model/runtime artifacts, which are not supplied here.
- The maintainer confirmed original-contribution ownership and approved inclusion of this patch under the root [Apache-2.0 license](../LICENSE), copyright 2026 dpotts34. Preserve the original upstream attribution, added modification notice, and retained license/notice files. See [NOTICE](../NOTICE) and [third-party credits](../THIRD_PARTY_NOTICES.md). A full native runtime, toolchain, or model distribution requires a separate review of its exact components; none is bundled here. Public publication remains a separate approval gate.

## Verification result

The original patch passed application checks with 8 insertions and 2 deletions. After adding only the two-line modification notice, a fresh exact-pin fetch and the same checker passed again: `src/asr/recognizer.cpp` was the only changed path (`10 insertions(+), 2 deletions(-)`). Upstream header lines and the three retained upstream notice files remain unchanged. Both checks prove source application only, not a build or inference run.