# Third-party credits and license scope

This source-only release retains all three optional advanced components. Bundled upstream patch material keeps its original notices; separately installed software is credited without being relicensed.

## Python dependency and tooling credits

### Distribution boundary

The reviewed intake wheel contains the project's Python modules and package metadata, not dependency modules, a Python interpreter, build tools, or test frameworks. The speech proxies and acceptance scripts use the Python standard library; the proxies invoke an operator-installed FFmpeg executable. The entries below credit separately installed software; they do not relicense it under the project's Apache-2.0 license.

The versions below describe the audited environment, **not a lockfile or a promise that every future installation resolves to these versions**. Direct requirements are `aiohttp>=3.11,<4`, `PyYAML>=6,<7`, and `markdown-it-py>=3,<5`, with Python `>=3.13`.

### Separately installed runtime packages

Copyright wording is retained where the upstream license states it. Author or maintainer metadata is not substituted for an unstated copyright notice.

| Package and upstream | Audited version | License and upstream attribution |
| --- | --- | --- |
| [aiohttp](https://github.com/aio-libs/aiohttp) — direct | 3.14.3 | Apache-2.0 AND MIT; `Copyright aio-libs contributors`; llhttp attribution below.[2] |
| [PyYAML](https://github.com/yaml/pyyaml) — direct | 6.0.3 | MIT; `Copyright (c) 2017-2021 Ingy döt Net`; `Copyright (c) 2006-2016 Kirill Simonov`.[21] |
| [markdown-it-py](https://github.com/executablebooks/markdown-it-py) — direct | 4.2.0 | MIT; `Copyright (c) 2020 ExecutableBookProject`; original and file-level notices below.[10] |
| [aiohappyeyeballs](https://github.com/aio-libs/aiohappyeyeballs) | 2.7.1 | PSF-2.0; the distributed license includes PSF and historical Python license notices, which must not be replaced with a generic Apache notice.[1] |
| [aiosignal](https://github.com/aio-libs/aiosignal) | 1.4.0 | Apache-2.0; `Copyright 2013-2019 Nikolay Kim and Andrew Svetlov`.[3] |
| [attrs](https://github.com/python-attrs/attrs) | 26.1.0 | MIT; `Copyright (c) 2015 Hynek Schlawack and the attrs contributors`.[4] |
| [frozenlist](https://github.com/aio-libs/frozenlist) | 1.8.0 | Apache-2.0; `Copyright 2013-2019 Nikolay Kim and Andrew Svetlov`.[5] |
| [multidict](https://github.com/aio-libs/multidict) | 6.9.1 | Apache-2.0; `Copyright aio-libs contributors`.[12] |
| [yarl](https://github.com/aio-libs/yarl) | 1.25.1 | Apache-2.0; NOTICE: `Copyright 2016-2021, Andrew Svetlov and aio-libs team`.[25] |
| [propcache](https://github.com/aio-libs/propcache) | 0.5.4 | Apache-2.0; NOTICE: `Copyright 2016-2021, Andrew Svetlov and aio-libs team`.[17] |
| [idna](https://github.com/kjd/idna) | 3.20 | BSD-3-Clause; `Copyright (c) 2013-2026, Kim Davies and contributors.`[8] |
| [mdurl](https://github.com/executablebooks/mdurl) | 0.1.2 | MIT; `Copyright (c) 2015 Vitaly Puzrin, Alex Kocharin.`; `Copyright (c) 2021 Taneli Hukkinen`; Node/Joyent notice below.[11] |

#### Embedded origins within those external distributions

- **llhttp 9.4.2**, the HTTP parser carried by aiohttp, is MIT-licensed: `Copyright © 2018 Fedor Indutny`. aiohttp supplies a separate `vendor/llhttp/LICENSE`; its source distribution identifies version 9.4.2.[2][31]
- **LibYAML 0.2.5**, present in the audited PyYAML native extension, is MIT-licensed: `Copyright (c) 2017-2020 Ingy döt Net` and `Copyright (c) 2006-2016 Kirill Simonov`. Its license is distinct from the PyYAML license even though both are MIT.[27]
- **markdown-it**, the JavaScript origin of markdown-it-py, is credited in `LICENSE.markdown-it`: `Copyright (c) 2014 Vitaly Puzrin, Alex Kocharin.` The Python package also carries an MIT notice in its punycode helper: `Copyright 2014 Mathias Bynens <https://mathiasbynens.be/>`, and `Copyright 2021 Taneli Hukkinen`.[10]
- **mdurl.js and Node.js/Joyent** origins are preserved in mdurl's license: `Copyright Joyent, Inc. and other Node contributors. All rights reserved.` Its parser also preserves an inline MIT notice.[11]

These embedded components are carried by the separately installed dependency distributions, **not by the reviewed project wheel**. If packaging those distributions into a combined installer, container, application bundle, or interpreter image, preserve their complete applicable license texts and inline notices. In particular, the audited PyYAML wheel carries its PyYAML license but no separate LibYAML license file; obtain and retain the exact LibYAML notice when redistributing that extension.[21][27]

### Python standard library

The project also uses **CPython and its standard library**; the audited interpreter is CPython 3.13.5. Python's license states PSF License Version 2 and retains the historical BeOpen, CNRI and CWI terms, with separate terms for some incorporated software. Its PSF notice is `Copyright (c) 2001-2024 Python Software Foundation; All Rights Reserved`. Do not reduce a redistributed interpreter or copied standard-library source to the project license.[26]

### Build and test tooling — not runtime requirements

`hatchling` is the declared project build backend. Build caches contain the versions listed below; the earlier build log did not record an exact resolved build environment, so **these observations are not proof of that historical build's complete version tuple**. pytest and its packages belong to preserved development-test evidence, not the shipped standard-library acceptance checker.

| Tool and upstream | Observed version(s) | License and attribution |
| --- | --- | --- |
| [uv](https://github.com/astral-sh/uv) | 0.11.2 executable | MIT OR Apache-2.0; `Copyright (c) 2025 Astral Software Inc.` The upstream licenses are alternatives, not an AND expression.[28][30] |
| [hatchling](https://github.com/pypa/hatch/tree/master/backend) | 1.32.0, 1.32.4 cached | MIT; Ofek Lev, with the exact upstream notice preserved in the tool's license.[6][7] |
| [packaging](https://github.com/pypa/packaging) | 26.3 in test environment; 26.0 and 26.3 cached | Apache-2.0 OR BSD-2-Clause; `Copyright (c) Donald Stufft and individual contributors.` Its license-expression module carries a separate MIT notice for Ofek Lev.[13][14] |
| [pathspec](https://github.com/cpburnz/python-pathspec) | 1.1.1 cached | **MPL-2.0**, not MIT or Apache-2.0; source metadata states `Copyright © 2013-2026 Caleb P. Burns`.[15] |
| [pluggy](https://github.com/pytest-dev/pluggy) | 1.6.0 test environment and cache | MIT; `Copyright (c) 2015 holger krekel (rather uses bitbucket/hpk42)`.[16] |
| [tomlkit](https://github.com/python-poetry/tomlkit) | 0.15.1 cached | MIT; `Copyright (c) 2018 Sébastien Eustace`.[22] |
| [trove-classifiers](https://github.com/pypa/trove-classifiers) | 2026.6.1.19, 2026.9.21.13 cached | Apache-2.0; the license contains a template, not a populated copyright-holder notice.[23][24] |
| [pytest](https://github.com/pytest-dev/pytest) | 9.1.1 test environment | MIT; `Copyright (c) 2004 Holger Krekel and others`.[19] |
| [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) | 1.4.0 test environment | Apache-2.0; the license contains a template, not a populated copyright-holder notice.[20] |
| [iniconfig](https://github.com/pytest-dev/iniconfig) | 2.3.0 test environment | MIT; `Copyright (c) 2010 - 2023 Holger Krekel and others`.[9] |
| [Pygments](https://github.com/pygments/pygments) | 2.21.0 test environment | BSD-2-Clause; `Copyright (c) 2006-2022 by the respective authors (see AUTHORS file).` Preserve the actual AUTHORS file if redistributing this package.[18] |

Additional upstream origins are recorded without treating them as project runtime requirements:

- packaging's generated license-identifier/deprecation map derives from **SPDX License List data 3.27.0**; the upstream generator and exact data-map match were checked. This credit does not assert a guessed license for the entire SPDX repository.[34][35]
- pytest identifies copied helpers from **py 1.8.1** and **CPython** in its source comments; these remain inside the external test distribution, not the project.[19]
- Building **PyYAML's own source distribution** on Python 3.13 requires setuptools and Cython `>=3.0`; these are conditional upstream build inputs, not additional dependencies of this project's wheel. The exact generator/compiler versions used to produce the audited extension were not established.[32]

### Minimal notice policy for this release

For the reviewed Python-only wheel, retain project licensing plus these descriptive credits; do not copy all external dependency source trees or a speculative collection of license files into it. Keep mandatory notices for actually bundled native-patch material separately; this Python audit does not replace them.

If later redistributing dependency/tool/interpreter material:

- **MIT:** retain the applicable copyright, permission notice and disclaimer, including embedded origins.[10][11]
- **Apache-2.0:** provide the license, preserve applicable source attribution and NOTICE content, and prominently mark modifications. yarl and propcache each supply a NOTICE.[25][17]
- **BSD:** retain/reproduce the copyright, conditions and disclaimer; BSD-3-Clause also prohibits unapproved endorsement.[8][18]
- **PSF/Python historical terms:** preserve applicable agreements and copyright notices; provide the required brief summary of changes to derivative Python material.[1][26]
- **MPL-2.0/pathspec:** covered source remains under MPL with notice/license access; distributing its executable form requires the corresponding covered source and instructions to obtain it. Using this external build tool does not make the project's own files MPL-covered.[15]

This is a bounded provenance and notice inventory, not certification of every upstream source file, an audit of FFmpeg/native/model binaries, or legal advice. No dependency or tool is relicensed here.


## External products and upstream material

The project Apache-2.0 license covers rights-confirmed original project contributions, not every tool, service, dependency or model it can use. The release does not bundle inference runtimes, model weights, FFmpeg, Git, Python, an ntfy server, or their toolchains. Separate-product credits below are not assertions that those products are redistributed or relicensed here.

### Included native patch material — preserve these notices

`patches/nemotron-asr-long-gpu-transducer.patch` contains context from `src/asr/recognizer.cpp` in **NVIDIA/NeMo-Speech.cpp**, upstream revision `9bc876635af36df537d9bc6d3f57ad1b76e4f74a`. That file carries NVIDIA's Apache-2.0 header; upstream NOTICE states: “Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.”[53][51]

The complete pinned upstream `LICENSE`, `NOTICE`, and `THIRD_PARTY_NOTICES.md` are preserved separately under `patches/licenses/`; this summary does not replace them. Apache-2.0 requires retaining applicable attribution, including the license and NOTICE, and prominent notices stating that modified files were changed.[50]

The upstream third-party notice credits ggml, llama.cpp/gguf-py, NVIDIA Riva protobuf definitions, Flashlight Text, CppJieba/limonp, cpp-httplib, whisper.cpp, parakeet.cpp, and tokenizer-data contributors. It also describes **LGPL-2.1-or-later KenLM with file-level exceptions**, BSD-licensed Open JTalk/MeCab/dictionary material, optional OpenSSL, and system libraries. Those implementations and data are not bundled here; their notices and exact build obligations must be reviewed if a combined upstream runtime is later distributed. Do not describe the complete upstream runtime as exclusively Apache-2.0.[52]

### Separately installed tools and services — informational credits

- **FFmpeg and its developers** provide audio conversion and tempo processing used by the advanced proxies and controlled checks. Licensing depends on the build: upstream distinguishes LGPL-2.1-or-later FFmpeg from GPL-enabled configurations. The recorded Debian `7.1.5-0+deb13u1` verification build reports **GPL version 2 or later**, not LGPL-only. No FFmpeg binary or library is distributed by this project. Redistribution of another build requires reviewing that exact build and its external libraries; this notice is not patent clearance.[36]
- **Opus/libopus** supplies the explicitly selected WebM/Opus encoder in the controlled proxy check. An Opus decoder and the appropriate demuxer are also needed, but the decoder need not be libopus. Opus carries BSD-style redistribution conditions.[49] Qwen proxy MP3 output leaves encoder selection to FFmpeg; the checked Debian build selects **LAME/libmp3lame**, a separately licensed library. Its upstream COPYING uses the GNU Library GPL.[56] FLAC and AAC output explicitly select FFmpeg's `flac` and `aac` encoders; AAC is emitted in ADTS, not M4A. These codec/container names are not separate proof of a library's license.[37]
- **Python and the Python Software Foundation** provide the interpreter and standard library. The recorded Python release has its own PSF and historical license terms.[26] **SQLite**, used through Python's `sqlite3`, dedicates its code and documentation to the public domain.[47]
- **Git** supplies the separately executed publication and patch-checking commands. Git's pinned COPYING specifies GPL version 2, unless explicitly otherwise stated; it is not project Apache-2.0 code.[38]
- **uv** is external installation/build tooling with MIT and Apache-2.0 license texts; **Hatch/Hatchling** supplies the declared build backend under MIT terms. Neither toolchain is bundled.[28][29][48]
- **ntfy**, by Philipp C. Heckel and contributors, supplies the notification HTTP protocol this project targets. The reviewed upstream server is dual licensed Apache-2.0/GPLv2. The client uses HTTP publishing and cached-event polling, not ntfy source or an SDK. No ntfy server or mobile app is included; the controlled notification receiver does not establish production-server or phone delivery.[64]

Linux/POSIX tools, curl, optional NFS/private networking, iPhone/iOS Shortcuts, Obsidian-compatible vaults and Git-host providers are external environment or documented integrations, not software distributions included in this release. Their exact installed products and service terms remain the operator's responsibility; no mobile app, exported Shortcut, operating-system image or hosting SDK is supplied.

### Speech runtime and model credits — distinct from project licensing

- **NVIDIA/NeMo-Speech.cpp** is the identified external native ASR runtime. Its pinned ggml and llama.cpp components carry MIT licenses, alongside the other upstream terms described above.[43][44][52]
- **ServeurpersoCom/qwentts.cpp**, runtime revision `a8a7716b530e49fed537c57711247c12fbbb903c`, is the identified external Qwen3-TTS C++/GGML port. Its MIT LICENSE credits “Copyright (c) 2023-2026 The omnivoice.cpp authors”; retain that wording rather than substituting a guessed holder. Its pinned ggml submodule is `c044c6f03892f9d5e98213b05f8afea1f8b0d3c9`, also MIT. This release includes neither that runtime nor its native patches.[40][41][42]
- **Qwen team / Alibaba** developed Qwen3-TTS. The identified `Serveurperso/Qwen3-TTS-GGUF` distribution and referenced `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` and `Qwen/Qwen3-TTS-Tokenizer-12Hz` model cards declare Apache-2.0. These are external model credits, not confirmation of a live endpoint's loaded artifact or blanket redistribution permission for every model alias.[66][68][69]
- The identified NVIDIA `nvidia/nemotron-speech-streaming-en-0.6b` model card names the **NVIDIA Open Model License**, not NeMo-Speech.cpp's Apache-2.0 software license. Actual checkpoint revision and GGUF conversion provenance require separate verification.[67]

ASR, TTS, structured-LLM and notification endpoints are operator-selected external services. “OpenAI-compatible” describes an HTTP interface, not an included OpenAI SDK or proof that OpenAI operates an endpoint. The tested `qwen-9b` identifier remains an alias with unresolved weight provenance and license; no model repository or license is inferred from it. Likewise, voice and compatibility identifiers do not establish artifact provenance or hardware support. No model download recommendation or bundled-model permission is implied by these credits.


## Sources

[1] https://files.pythonhosted.org/packages/71/43/1947f06babed6b3f1d7f38b0c767f52df66bfb2bc10b468c4a7de9eceff2/aiohappyeyeballs-2.7.1-py3-none-any.whl — aiohappyeyeballs 2.7.1: exact released wheel license texts
[2] https://files.pythonhosted.org/packages/ca/1c/7da8d08e74d56f00070822f9638ff3f1c563f8ad87d1efa996c87bfc8644/aiohttp-3.14.3-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl — aiohttp 3.14.3: exact released wheel license texts
[3] https://files.pythonhosted.org/packages/fb/76/641ae371508676492379f16e2fa48f4e2c11741bd63c48be4b12a6b09cba/aiosignal-1.4.0-py3-none-any.whl — aiosignal 1.4.0: exact released wheel license texts
[4] https://files.pythonhosted.org/packages/64/b4/17d4b0b2a2dc85a6df63d1157e028ed19f90d4cd97c36717afef2bc2f395/attrs-26.1.0-py3-none-any.whl — attrs 26.1.0: exact released wheel license texts
[5] https://files.pythonhosted.org/packages/d5/4e/e4691508f9477ce67da2015d8c00acd751e6287739123113a9fca6f1604e/frozenlist-1.8.0-cp313-cp313-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl — frozenlist 1.8.0: exact released wheel license texts
[6] https://files.pythonhosted.org/packages/a9/84/1798b6d85ecde0e31546004efd25c5de1b1f49250644a60cce460e12593a/hatchling-1.32.0-py3-none-any.whl — hatchling 1.32.0: exact released wheel license texts
[7] https://files.pythonhosted.org/packages/5f/80/91f51f439c05d4ec4623c22928ce16a938d6d793bf709477830823497859/hatchling-1.32.4-py3-none-any.whl — hatchling 1.32.4: exact released wheel license texts
[8] https://files.pythonhosted.org/packages/58/a2/bb081bab032533a855d44de1d56f8e8426114ff1ba5d1f07a438a0a654f8/idna-3.20-py3-none-any.whl — idna 3.20: exact released wheel license texts
[9] https://files.pythonhosted.org/packages/cb/b1/3846dd7f199d53cb17f49cba7e651e9ce294d8497c8c150530ed11865bb8/iniconfig-2.3.0-py3-none-any.whl — iniconfig 2.3.0: exact released wheel license texts
[10] https://files.pythonhosted.org/packages/b3/81/4da04ced5a082363ecfa159c010d200ecbd959ae410c10c0264a38cac0f5/markdown_it_py-4.2.0-py3-none-any.whl — markdown-it-py 4.2.0: exact released wheel license texts
[11] https://files.pythonhosted.org/packages/b3/38/89ba8ad64ae25be8de66a6d463314cf1eb366222074cfda9ee839c56a4b4/mdurl-0.1.2-py3-none-any.whl — mdurl 0.1.2: exact released wheel license texts
[12] https://files.pythonhosted.org/packages/93/f2/e06c8e42074d0a4b8419bfe92afbd1d262190b69549ecbcd2dffa4f103c2/multidict-6.9.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl — multidict 6.9.1: exact released wheel license texts
[13] https://files.pythonhosted.org/packages/b7/b9/c538f279a4e237a006a2c98387d081e9eb060d203d8ed34467cc0f0b9b53/packaging-26.0-py3-none-any.whl — packaging 26.0: exact released wheel license texts
[14] https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl — packaging 26.3: exact released wheel license texts
[15] https://files.pythonhosted.org/packages/f1/d9/7fb5aa316bc299258e68c73ba3bddbc499654a07f151cba08f6153988714/pathspec-1.1.1-py3-none-any.whl — pathspec 1.1.1: exact released wheel license texts
[16] https://files.pythonhosted.org/packages/54/20/4d324d65cc6d9205fabedc306948156824eb9f0ee1633355a8f7ec5c66bf/pluggy-1.6.0-py3-none-any.whl — pluggy 1.6.0: exact released wheel license texts
[17] https://files.pythonhosted.org/packages/ed/74/08e6c1faf26ee2732023a3828787ba535557122774f4a386b1f715cbd8e0/propcache-0.5.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl — propcache 0.5.4: exact released wheel license texts
[18] https://files.pythonhosted.org/packages/71/46/17f022dd3e953bf20a04a028a21ec746d942f8d2af30fa0f124fa0e6a684/pygments-2.21.0-py3-none-any.whl — Pygments 2.21.0: exact released wheel license texts
[19] https://files.pythonhosted.org/packages/24/25/1de2678b631f5a49215c6c96fff41ba892b0a34df68d6d80292b1b48aa7f/pytest-9.1.1-py3-none-any.whl — pytest 9.1.1: exact released wheel license texts
[20] https://files.pythonhosted.org/packages/03/e2/08a497ef684b88559c9cc5f4ad53a37e7b99e727094a86d6ea32536d5d3c/pytest_asyncio-1.4.0-py3-none-any.whl — pytest-asyncio 1.4.0: exact released wheel license texts
[21] https://files.pythonhosted.org/packages/74/27/e5b8f34d02d9995b80abcef563ea1f8b56d20134d8f4e5e81733b1feceb2/pyyaml-6.0.3-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl — PyYAML 6.0.3: exact released wheel license texts
[22] https://files.pythonhosted.org/packages/13/bc/8c13eb66537dce1d2bd3a57132902f38d0e7f5bb46fa9f4daed9fe9d76ee/tomlkit-0.15.1-py3-none-any.whl — tomlkit 0.15.1: exact released wheel license texts
[23] https://files.pythonhosted.org/packages/7c/a4/81502f486f01db95bc8320646a8a12511f5e556cb63d5e224d91816605c4/trove_classifiers-2026.6.1.19-py3-none-any.whl — trove-classifiers 2026.6.1.19: exact released wheel license texts
[24] https://files.pythonhosted.org/packages/30/81/0da8afb52a71d0a4f2bd3152357b1a441e393b286374802b9d3addab4ab5/trove_classifiers-2026.9.21.13-py3-none-any.whl — trove-classifiers 2026.9.21.13: exact released wheel license texts
[25] https://files.pythonhosted.org/packages/0e/b7/a82a49bf88340b837ef6972b508a1604ae377b9e6904b46b10cf5f1cf925/yarl-1.25.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl — yarl 1.25.1: exact released wheel license texts
[26] https://raw.githubusercontent.com/python/cpython/v3.13.5/LICENSE — CPython 3.13.5 license
[27] https://raw.githubusercontent.com/yaml/libyaml/0.2.5/License — LibYAML 0.2.5 MIT license
[28] https://raw.githubusercontent.com/astral-sh/uv/0.11.2/LICENSE-MIT — uv 0.11.2 MIT license
[29] https://raw.githubusercontent.com/astral-sh/uv/0.11.2/LICENSE-APACHE — uv 0.11.2 Apache license
[30] https://raw.githubusercontent.com/astral-sh/uv/0.11.2/README.md — uv 0.11.2 README license choice
[31] https://files.pythonhosted.org/packages/58/d9/22ce5786ac0c1653ae8b6c23bded02c1686d11f0dbb45b31ce128e0df985/aiohttp-3.14.3.tar.gz — aiohttp 3.14.3 source distribution: embedded origin/build evidence
[32] https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz — PyYAML 6.0.3 source distribution: embedded origin/build evidence
[34] https://raw.githubusercontent.com/pypa/packaging/26.3/tasks/licenses.py — packaging 26.3 SPDX generator
[35] https://raw.githubusercontent.com/spdx/license-list-data/v3.27.0/README.md — SPDX License List data 3.27.0 README
[36] https://ffmpeg.org/legal.html — ffmpeg-legal
[37] https://ffmpeg.org/ffmpeg-codecs.html — ffmpeg-codecs
[38] https://raw.githubusercontent.com/git/git/v2.47.3/COPYING — git-copying
[40] https://raw.githubusercontent.com/ServeurpersoCom/qwentts.cpp/a8a7716b530e49fed537c57711247c12fbbb903c/LICENSE — qwentts-license
[41] https://raw.githubusercontent.com/ServeurpersoCom/qwentts.cpp/a8a7716b530e49fed537c57711247c12fbbb903c/README.md — qwentts-readme
[42] https://raw.githubusercontent.com/ggml-org/ggml/c044c6f03892f9d5e98213b05f8afea1f8b0d3c9/LICENSE — qwentts-ggml-license
[43] https://raw.githubusercontent.com/ggml-org/ggml/c03b4e2bcece5134827881af90242086daf75be5/LICENSE — nemo-ggml-license
[44] https://raw.githubusercontent.com/ggml-org/llama.cpp/560445bf34c87356ad0f8d80fb03ec5488850b65/LICENSE — nemo-llama-license
[47] https://www.sqlite.org/copyright.html — sqlite-copyright
[48] https://raw.githubusercontent.com/pypa/hatch/master/LICENSE.txt — hatch-license
[49] https://raw.githubusercontent.com/xiph/opus/main/COPYING — opus-copying
[50] https://raw.githubusercontent.com/NVIDIA/NeMo-Speech.cpp/9bc876635af36df537d9bc6d3f57ad1b76e4f74a/LICENSE — nemo-license-web
[51] https://raw.githubusercontent.com/NVIDIA/NeMo-Speech.cpp/9bc876635af36df537d9bc6d3f57ad1b76e4f74a/NOTICE — nemo-notice-web
[52] https://raw.githubusercontent.com/NVIDIA/NeMo-Speech.cpp/9bc876635af36df537d9bc6d3f57ad1b76e4f74a/THIRD_PARTY_NOTICES.md — nemo-thirdparty-web
[53] https://raw.githubusercontent.com/NVIDIA/NeMo-Speech.cpp/9bc876635af36df537d9bc6d3f57ad1b76e4f74a/src/asr/recognizer.cpp — nemo-recognizer-web
[56] https://raw.githubusercontent.com/rbrito/lame/master/COPYING — lame-license
[64] https://raw.githubusercontent.com/binwiederhier/ntfy/8b95a3bbfd42d40a16293b6e2079b104bf6eb68d/README.md — ntfy-readme-pinned
[66] https://huggingface.co/Serveurperso/Qwen3-TTS-GGUF/raw/b7ee2e8c7459c3bea99da23e3d178125a7d1713c/README.md — qwen-quant-card-pinned
[67] https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b/raw/ebe59e5a817142986528bbbee5dba8db7b38ed50/README.md — nemotron-model-card-pinned
[68] https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice/raw/85e237c12c027371202489a0ec509ded67b5e4b5/README.md — qwen-original-card-pinned
[69] https://huggingface.co/Qwen/Qwen3-TTS-Tokenizer-12Hz/raw/7dd38ad4e9bad454aae9cd937d0cd577604fe229/README.md — qwen-tokenizer-card-pinned
