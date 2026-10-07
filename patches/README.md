# Native speech-recognition patch

One source patch, not the full private patch set. No upstream checkout, submodules, models, binaries, build output, benchmarks, or machine-specific evidence.

## Source and behavior

| Patch | Upstream | Exact base revision |
| --- | --- | --- |
| `nemotron-asr-long-gpu-transducer.patch` | [NVIDIA/NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp) | `9bc876635af36df537d9bc6d3f57ad1b76e4f74a` |

GPU offline audio longer than 10 seconds uses the existing cache-streaming runner. Requires a non-CTC transducer model, usable sample rate, and model cache-streaming support. Fixed threshold, not a hardware recommendation.

Captured private-source change. Wording and local constant name changed, logic and threshold unchanged. Other GGML/Qwen3-TTS patches excluded.

## Apply and check

Requires Git and upstream HTTPS access. From this repository root:

```sh
work=$(mktemp -d)
git clone --filter=blob:none --no-checkout https://github.com/NVIDIA/NeMo-Speech.cpp.git "$work/NeMo-Speech.cpp"
git -C "$work/NeMo-Speech.cpp" fetch --depth=1 origin 9bc876635af36df537d9bc6d3f57ad1b76e4f74a
git -C "$work/NeMo-Speech.cpp" checkout --detach 9bc876635af36df537d9bc6d3f57ad1b76e4f74a
./patches/verify-application.sh "$work/NeMo-Speech.cpp"
```

Use a fresh disposable checkout each run. Checker rejects changed files or wrong revision. Runs `git apply --check`, applies at root, checks whitespace, and permits changes only to `src/asr/recognizer.cpp`. No submodules needed. Success modifies that file.

## What the check proves

Original patch passed, 8 insertions and 2 deletions. Added two-line modification notice, then retested on a fresh pinned checkout. Only `src/asr/recognizer.cpp` changed, `10 insertions(+), 2 deletions(-)`. Upstream header and three retained notice files unchanged.

Proves patch application only. No native/GPU build, inference, speed, stability, or GPU/CUDA/ROCm/driver/model compatibility claim. Applies only to the pinned revision without adaptation. Builds/runs require upstream prerequisites and compatible model/runtime files, not supplied.

## Licenses and publication

`licenses/` keeps upstream `LICENSE`, `NOTICE`, and `THIRD_PARTY_NOTICES.md` unchanged from the pinned revision. Patch includes recognizer context only. Adds a modification notice after the unchanged two-line copyright/license header.

Maintainer confirmed ownership and approved [Apache-2.0](../LICENSE). Copyright 2026 dpotts34. Keep upstream attribution, modification notice, and license/notice files. See [NOTICE](../NOTICE) and [credits](../THIRD_PARTY_NOTICES.md).

Upstream notices summarize dependencies. Check each before building/redistributing combined material. Native runtimes, toolchains, and models need a separate component/license review. None bundled. Public publication needs separate approval.
