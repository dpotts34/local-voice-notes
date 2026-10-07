# Third-party credits and license scope

Source only. Includes intake, two speech proxies, and one native patch. Upstream material keeps its licenses and notices.

## Python dependency and tooling credits

### Distribution boundary

Intake package contains project Python modules and metadata only. No dependencies, Python, build tools, or test frameworks bundled. Proxies and checks use the standard library. Proxies call your FFmpeg installation. Project Apache-2.0 does not relicense external software.

Audited versions, not locked future installs. Requires `aiohttp>=3.11,<4`, `PyYAML>=6,<7`, `markdown-it-py>=3,<5`, Python `>=3.13`.

### Separately installed runtime packages

Copyright text is upstream's. Author/maintainer names do not replace missing notices.

| Package and upstream | Audited version | License and upstream attribution |
| --- | --- | --- |
| [aiohttp](https://github.com/aio-libs/aiohttp), direct | 3.14.3 | Apache-2.0 AND MIT; `Copyright aio-libs contributors`; llhttp attribution below.[2] |
| [PyYAML](https://github.com/yaml/pyyaml), direct | 6.0.3 | MIT; `Copyright (c) 2017-2021 Ingy döt Net`; `Copyright (c) 2006-2016 Kirill Simonov`.[21] |
| [markdown-it-py](https://github.com/executablebooks/markdown-it-py), direct | 4.2.0 | MIT; `Copyright (c) 2020 ExecutableBookProject`; original and file-level notices below.[10] |
| [aiohappyeyeballs](https://github.com/aio-libs/aiohappyeyeballs) | 2.7.1 | PSF-2.0; retain PSF and historical Python notices, not a generic Apache notice.[1] |
| [aiosignal](https://github.com/aio-libs/aiosignal) | 1.4.0 | Apache-2.0; `Copyright 2013-2019 Nikolay Kim and Andrew Svetlov`.[3] |
| [attrs](https://github.com/python-attrs/attrs) | 26.1.0 | MIT; `Copyright (c) 2015 Hynek Schlawack and the attrs contributors`.[4] |
| [frozenlist](https://github.com/aio-libs/frozenlist) | 1.8.0 | Apache-2.0; `Copyright 2013-2019 Nikolay Kim and Andrew Svetlov`.[5] |
| [multidict](https://github.com/aio-libs/multidict) | 6.9.1 | Apache-2.0; `Copyright aio-libs contributors`.[12] |
| [yarl](https://github.com/aio-libs/yarl) | 1.25.1 | Apache-2.0; NOTICE: `Copyright 2016-2021, Andrew Svetlov and aio-libs team`.[25] |
| [propcache](https://github.com/aio-libs/propcache) | 0.5.4 | Apache-2.0; NOTICE: `Copyright 2016-2021, Andrew Svetlov and aio-libs team`.[17] |
| [idna](https://github.com/kjd/idna) | 3.20 | BSD-3-Clause; `Copyright (c) 2013-2026, Kim Davies and contributors.`[8] |
| [mdurl](https://github.com/executablebooks/mdurl) | 0.1.2 | MIT; `Copyright (c) 2015 Vitaly Puzrin, Alex Kocharin.`; `Copyright (c) 2021 Taneli Hukkinen`; Node/Joyent notice below.[11] |

#### Code included in external packages

- llhttp 9.4.2 is aiohttp's MIT HTTP parser. `Copyright © 2018 Fedor Indutny`. aiohttp includes `vendor/llhttp/LICENSE`; its source distribution identifies version 9.4.2.[2][31]
- LibYAML 0.2.5 is in the audited PyYAML native extension. MIT; `Copyright (c) 2017-2020 Ingy döt Net` and `Copyright (c) 2006-2016 Kirill Simonov`. Its license is separate from PyYAML's MIT license.[27]
- markdown-it is markdown-it-py's JavaScript origin. `LICENSE.markdown-it` credits `Copyright (c) 2014 Vitaly Puzrin, Alex Kocharin.` The Python punycode helper has an MIT notice with `Copyright 2014 Mathias Bynens <https://mathiasbynens.be/>` and `Copyright 2021 Taneli Hukkinen`.[10]
- mdurl.js and Node.js/Joyent are credited in mdurl's license. `Copyright Joyent, Inc. and other Node contributors. All rights reserved.` The parser also has an inline MIT notice.[11]

External packages only. Bundling them requires all applicable license texts and inline notices. Audited PyYAML lacks a separate LibYAML license file. Obtain the exact notice before redistributing its extension.[21][27]

### Python standard library

The project uses CPython and its standard library. The audited interpreter is CPython 3.13.5. Its license includes PSF License Version 2, historical BeOpen, CNRI and CWI terms, and separate terms for some included software. `Copyright (c) 2001-2024 Python Software Foundation; All Rights Reserved`. Redistributed Python and copied standard-library source retain their own terms.[26]

### Build and test tools, not runtime requirements

`hatchling` builds the package. Cached versions do not identify the earlier build environment, absent from its log. pytest packages appear in saved development tests, not the shipped standard-library checker.

| Tool and upstream | Observed versions | License and attribution |
| --- | --- | --- |
| [uv](https://github.com/astral-sh/uv) | 0.11.2 executable | MIT OR Apache-2.0; `Copyright (c) 2025 Astral Software Inc.` Alternative licenses, not AND.[28][30] |
| [hatchling](https://github.com/pypa/hatch/tree/master/backend) | 1.32.0, 1.32.4 cached | MIT; Ofek Lev. Retain the exact notice in the tool's license.[6][7] |
| [packaging](https://github.com/pypa/packaging) | 26.3 in test environment; 26.0 and 26.3 cached | Apache-2.0 OR BSD-2-Clause; `Copyright (c) Donald Stufft and individual contributors.` Its license-expression module carries a separate MIT notice for Ofek Lev.[13][14] |
| [pathspec](https://github.com/cpburnz/python-pathspec) | 1.1.1 cached | MPL-2.0, not MIT or Apache-2.0; source metadata states `Copyright © 2013-2026 Caleb P. Burns`.[15] |
| [pluggy](https://github.com/pytest-dev/pluggy) | 1.6.0 test environment and cache | MIT; `Copyright (c) 2015 holger krekel (rather uses bitbucket/hpk42)`.[16] |
| [tomlkit](https://github.com/python-poetry/tomlkit) | 0.15.1 cached | MIT; `Copyright (c) 2018 Sébastien Eustace`.[22] |
| [trove-classifiers](https://github.com/pypa/trove-classifiers) | 2026.6.1.19, 2026.9.21.13 cached | Apache-2.0; the license contains a template, not a populated copyright-holder notice.[23][24] |
| [pytest](https://github.com/pytest-dev/pytest) | 9.1.1 test environment | MIT; `Copyright (c) 2004 Holger Krekel and others`.[19] |
| [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) | 1.4.0 test environment | Apache-2.0; the license contains a template, not a populated copyright-holder notice.[20] |
| [iniconfig](https://github.com/pytest-dev/iniconfig) | 2.3.0 test environment | MIT; `Copyright (c) 2010 - 2023 Holger Krekel and others`.[9] |
| [Pygments](https://github.com/pygments/pygments) | 2.21.0 test environment | BSD-2-Clause; `Copyright (c) 2006-2022 by the respective authors (see AUTHORS file).` Preserve the actual AUTHORS file if redistributing this package.[18] |

Other upstream code and data, not project runtime requirements:

- packaging's license-identifier/deprecation map uses SPDX License List data 3.27.0. The generator and exact data-map match were checked. This does not assign a license to the whole SPDX repository.[34][35]
- pytest source comments credit helpers copied from py 1.8.1 and CPython. They remain in the external test package, not the project.[19]
- Building PyYAML's source distribution on Python 3.13 needs setuptools and Cython `>=3.0`. These are upstream build inputs, not project wheel dependencies. The audited extension's exact generator/compiler versions are unknown.[32]

### Notices to retain

Python-only package needs project licensing and these credits, not unbundled dependency sources/licenses. Native patches need separate notices. This audit does not replace them.

If you redistribute dependencies, tools or Python:

- MIT: retain copyright, permission notices and disclaimers, including those for embedded code.[10][11]
- Apache-2.0: provide the license, retain applicable source attribution and NOTICE content, and prominently mark changes. yarl and propcache each have a NOTICE.[25][17]
- BSD: retain/reproduce copyright, conditions and disclaimers. BSD-3-Clause also prohibits unapproved endorsement.[8][18]
- PSF/Python historical terms: retain applicable agreements and copyright notices. Include the required brief summary of changes to derivative Python material.[1][26]
- MPL-2.0/pathspec: covered source stays under MPL with access to notices and the license. Executable distribution requires corresponding covered source and instructions to obtain it. Using pathspec does not make project files MPL-covered.[15]

Not a full upstream-file or binary audit. Not legal advice. No dependency/tool relicensing.


## External products and upstream material

Apache-2.0 covers confirmed original contributions only. No inference runtimes, model weights, FFmpeg, Git, Python, ntfy servers, or toolchains bundled or relicensed.

### Included native patches

`patches/nemotron-asr-long-gpu-transducer.patch` includes NVIDIA/NeMo-Speech.cpp's `src/asr/recognizer.cpp` context at `9bc876635af36df537d9bc6d3f57ad1b76e4f74a`. NVIDIA Apache-2.0 header. Upstream NOTICE states `Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.`[53][51]

Complete pinned upstream `LICENSE`, `NOTICE` and `THIRD_PARTY_NOTICES.md` remain in `patches/licenses/`. This summary does not replace them. Apache-2.0 requires applicable attribution, the license and NOTICE, and prominent notices on modified files stating they were changed.[50]

Upstream notices credit ggml, llama.cpp/gguf-py, NVIDIA Riva protobuf definitions, Flashlight Text, CppJieba/limonp, cpp-httplib, whisper.cpp, parakeet.cpp and tokenizer-data contributors. They cover LGPL-2.1-or-later KenLM with file-level exceptions, BSD-licensed Open JTalk/MeCab/dictionary material, optional OpenSSL and system libraries. This release excludes that code and data. Review their notices and exact build obligations before distributing a combined runtime. The full upstream runtime is not exclusively Apache-2.0.[52]

### External tools and services

- FFmpeg and its developers provide audio conversion and tempo processing for advanced proxies and controlled checks. Build terms vary between LGPL-2.1-or-later and GPL-enabled configurations. The checked Debian `7.1.5-0+deb13u1` build reports GPL version 2 or later, not LGPL-only. This project distributes no FFmpeg binary or library. Review the exact build and external libraries before redistribution. This notice is not patent clearance.[36]
- Opus/libopus is the selected WebM/Opus encoder in the controlled proxy check. It also needs an Opus decoder and suitable demuxer; the decoder need not be libopus. Opus has BSD-style redistribution conditions.[49] Qwen proxy MP3 output lets FFmpeg choose the encoder. The checked Debian build selects LAME/libmp3lame, whose separate COPYING uses GNU Library GPL.[56] FLAC and AAC output select FFmpeg's `flac` and `aac` encoders. AAC uses ADTS, not M4A. Codec/container names do not prove a library's license.[37]
- Python and the Python Software Foundation provide the interpreter and standard library under PSF and historical terms.[26] SQLite, used through Python's `sqlite3`, dedicates code and documentation to the public domain.[47]
- Git runs publication and patch checks. Its pinned COPYING specifies GPL version 2 unless explicitly stated otherwise, not project Apache-2.0.[38]
- uv installs/builds software under MIT or Apache-2.0 terms. Hatch/Hatchling is the MIT build backend. Neither toolchain is bundled.[28][29][48]
- ntfy, by Philipp C. Heckel and contributors, defines the notification HTTP protocol used here. The reviewed server is dual licensed Apache-2.0/GPLv2. The client publishes and polls cached events over HTTP, without ntfy source or an SDK. No ntfy server or mobile app is included. The controlled receiver does not prove production-server or phone delivery.[64]

Linux/POSIX tools, curl, optional NFS/private networking, iPhone/iOS Shortcuts, Obsidian-compatible vaults and Git-host providers are external tools or integrations. Operators must check their installed products and service terms. This release includes no mobile app, exported Shortcut, operating-system image or hosting SDK.

### External speech runtimes and models

- NVIDIA/NeMo-Speech.cpp is the identified external native ASR runtime. Its pinned ggml and llama.cpp components use MIT, with other upstream terms listed above.[43][44][52]
- ServeurpersoCom/qwentts.cpp at `a8a7716b530e49fed537c57711247c12fbbb903c` is the external Qwen3-TTS C++/GGML port. MIT LICENSE credits `Copyright (c) 2023-2026 The omnivoice.cpp authors`. Preserve that holder. Its MIT ggml submodule is pinned to `c044c6f03892f9d5e98213b05f8afea1f8b0d3c9`. Runtime and native patches not bundled.[40][41][42]
- Qwen team / Alibaba developed Qwen3-TTS. Model cards for `Serveurperso/Qwen3-TTS-GGUF`, `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` and `Qwen/Qwen3-TTS-Tokenizer-12Hz` declare Apache-2.0. These credits do not confirm a live endpoint's loaded artifact or give blanket redistribution permission for model aliases.[66][68][69]
- NVIDIA's `nvidia/nemotron-speech-streaming-en-0.6b` model card names NVIDIA Open Model License, not NeMo-Speech.cpp's Apache-2.0 software license. Verify the actual checkpoint revision and GGUF conversion source separately.[67]

Operators select external ASR, TTS, structured-LLM and notification services. "OpenAI-compatible" means an HTTP interface, not an included OpenAI SDK or proof of an OpenAI-operated endpoint. The tested `qwen-9b` alias has unknown weight source and license. It does not identify a model repository or license. Voice and compatibility identifiers do not prove artifact source or hardware support. These credits do not recommend model downloads or grant permission to bundle models.


## Sources

[1] https://files.pythonhosted.org/packages/71/43/1947f06babed6b3f1d7f38b0c767f52df66bfb2bc10b468c4a7de9eceff2/aiohappyeyeballs-2.7.1-py3-none-any.whl
[2] https://files.pythonhosted.org/packages/ca/1c/7da8d08e74d56f00070822f9638ff3f1c563f8ad87d1efa996c87bfc8644/aiohttp-3.14.3-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
[3] https://files.pythonhosted.org/packages/fb/76/641ae371508676492379f16e2fa48f4e2c11741bd63c48be4b12a6b09cba/aiosignal-1.4.0-py3-none-any.whl
[4] https://files.pythonhosted.org/packages/64/b4/17d4b0b2a2dc85a6df63d1157e028ed19f90d4cd97c36717afef2bc2f395/attrs-26.1.0-py3-none-any.whl
[5] https://files.pythonhosted.org/packages/d5/4e/e4691508f9477ce67da2015d8c00acd751e6287739123113a9fca6f1604e/frozenlist-1.8.0-cp313-cp313-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl
[6] https://files.pythonhosted.org/packages/a9/84/1798b6d85ecde0e31546004efd25c5de1b1f49250644a60cce460e12593a/hatchling-1.32.0-py3-none-any.whl
[7] https://files.pythonhosted.org/packages/5f/80/91f51f439c05d4ec4623c22928ce16a938d6d793bf709477830823497859/hatchling-1.32.4-py3-none-any.whl
[8] https://files.pythonhosted.org/packages/58/a2/bb081bab032533a855d44de1d56f8e8426114ff1ba5d1f07a438a0a654f8/idna-3.20-py3-none-any.whl
[9] https://files.pythonhosted.org/packages/cb/b1/3846dd7f199d53cb17f49cba7e651e9ce294d8497c8c150530ed11865bb8/iniconfig-2.3.0-py3-none-any.whl
[10] https://files.pythonhosted.org/packages/b3/81/4da04ced5a082363ecfa159c010d200ecbd959ae410c10c0264a38cac0f5/markdown_it_py-4.2.0-py3-none-any.whl
[11] https://files.pythonhosted.org/packages/b3/38/89ba8ad64ae25be8de66a6d463314cf1eb366222074cfda9ee839c56a4b4/mdurl-0.1.2-py3-none-any.whl
[12] https://files.pythonhosted.org/packages/93/f2/e06c8e42074d0a4b8419bfe92afbd1d262190b69549ecbcd2dffa4f103c2/multidict-6.9.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
[13] https://files.pythonhosted.org/packages/b7/b9/c538f279a4e237a006a2c98387d081e9eb060d203d8ed34467cc0f0b9b53/packaging-26.0-py3-none-any.whl
[14] https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl
[15] https://files.pythonhosted.org/packages/f1/d9/7fb5aa316bc299258e68c73ba3bddbc499654a07f151cba08f6153988714/pathspec-1.1.1-py3-none-any.whl
[16] https://files.pythonhosted.org/packages/54/20/4d324d65cc6d9205fabedc306948156824eb9f0ee1633355a8f7ec5c66bf/pluggy-1.6.0-py3-none-any.whl
[17] https://files.pythonhosted.org/packages/ed/74/08e6c1faf26ee2732023a3828787ba535557122774f4a386b1f715cbd8e0/propcache-0.5.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
[18] https://files.pythonhosted.org/packages/71/46/17f022dd3e953bf20a04a028a21ec746d942f8d2af30fa0f124fa0e6a684/pygments-2.21.0-py3-none-any.whl
[19] https://files.pythonhosted.org/packages/24/25/1de2678b631f5a49215c6c96fff41ba892b0a34df68d6d80292b1b48aa7f/pytest-9.1.1-py3-none-any.whl
[20] https://files.pythonhosted.org/packages/03/e2/08a497ef684b88559c9cc5f4ad53a37e7b99e727094a86d6ea32536d5d3c/pytest_asyncio-1.4.0-py3-none-any.whl
[21] https://files.pythonhosted.org/packages/74/27/e5b8f34d02d9995b80abcef563ea1f8b56d20134d8f4e5e81733b1feceb2/pyyaml-6.0.3-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
[22] https://files.pythonhosted.org/packages/13/bc/8c13eb66537dce1d2bd3a57132902f38d0e7f5bb46fa9f4daed9fe9d76ee/tomlkit-0.15.1-py3-none-any.whl
[23] https://files.pythonhosted.org/packages/7c/a4/81502f486f01db95bc8320646a8a12511f5e556cb63d5e224d91816605c4/trove_classifiers-2026.6.1.19-py3-none-any.whl
[24] https://files.pythonhosted.org/packages/30/81/0da8afb52a71d0a4f2bd3152357b1a441e393b286374802b9d3addab4ab5/trove_classifiers-2026.9.21.13-py3-none-any.whl
[25] https://files.pythonhosted.org/packages/0e/b7/a82a49bf88340b837ef6972b508a1604ae377b9e6904b46b10cf5f1cf925/yarl-1.25.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
[26] https://raw.githubusercontent.com/python/cpython/v3.13.5/LICENSE
[27] https://raw.githubusercontent.com/yaml/libyaml/0.2.5/License
[28] https://raw.githubusercontent.com/astral-sh/uv/0.11.2/LICENSE-MIT
[29] https://raw.githubusercontent.com/astral-sh/uv/0.11.2/LICENSE-APACHE
[30] https://raw.githubusercontent.com/astral-sh/uv/0.11.2/README.md
[31] https://files.pythonhosted.org/packages/58/d9/22ce5786ac0c1653ae8b6c23bded02c1686d11f0dbb45b31ce128e0df985/aiohttp-3.14.3.tar.gz
[32] https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz
[34] https://raw.githubusercontent.com/pypa/packaging/26.3/tasks/licenses.py
[35] https://raw.githubusercontent.com/spdx/license-list-data/v3.27.0/README.md
[36] https://ffmpeg.org/legal.html
[37] https://ffmpeg.org/ffmpeg-codecs.html
[38] https://raw.githubusercontent.com/git/git/v2.47.3/COPYING
[40] https://raw.githubusercontent.com/ServeurpersoCom/qwentts.cpp/a8a7716b530e49fed537c57711247c12fbbb903c/LICENSE
[41] https://raw.githubusercontent.com/ServeurpersoCom/qwentts.cpp/a8a7716b530e49fed537c57711247c12fbbb903c/README.md
[42] https://raw.githubusercontent.com/ggml-org/ggml/c044c6f03892f9d5e98213b05f8afea1f8b0d3c9/LICENSE
[43] https://raw.githubusercontent.com/ggml-org/ggml/c03b4e2bcece5134827881af90242086daf75be5/LICENSE
[44] https://raw.githubusercontent.com/ggml-org/llama.cpp/560445bf34c87356ad0f8d80fb03ec5488850b65/LICENSE
[47] https://www.sqlite.org/copyright.html
[48] https://raw.githubusercontent.com/pypa/hatch/master/LICENSE.txt
[49] https://raw.githubusercontent.com/xiph/opus/main/COPYING
[50] https://raw.githubusercontent.com/NVIDIA/NeMo-Speech.cpp/9bc876635af36df537d9bc6d3f57ad1b76e4f74a/LICENSE
[51] https://raw.githubusercontent.com/NVIDIA/NeMo-Speech.cpp/9bc876635af36df537d9bc6d3f57ad1b76e4f74a/NOTICE
[52] https://raw.githubusercontent.com/NVIDIA/NeMo-Speech.cpp/9bc876635af36df537d9bc6d3f57ad1b76e4f74a/THIRD_PARTY_NOTICES.md
[53] https://raw.githubusercontent.com/NVIDIA/NeMo-Speech.cpp/9bc876635af36df537d9bc6d3f57ad1b76e4f74a/src/asr/recognizer.cpp
[56] https://raw.githubusercontent.com/rbrito/lame/master/COPYING
[64] https://raw.githubusercontent.com/binwiederhier/ntfy/8b95a3bbfd42d40a16293b6e2079b104bf6eb68d/README.md
[66] https://huggingface.co/Serveurperso/Qwen3-TTS-GGUF/raw/b7ee2e8c7459c3bea99da23e3d178125a7d1713c/README.md
[67] https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b/raw/ebe59e5a817142986528bbbee5dba8db7b38ed50/README.md
[68] https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice/raw/85e237c12c027371202489a0ec509ded67b5e4b5/README.md
[69] https://huggingface.co/Qwen/Qwen3-TTS-Tokenizer-12Hz/raw/7dd38ad4e9bad454aae9cd937d0cd577604fe229/README.md
