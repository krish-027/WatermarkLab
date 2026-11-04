# MarkLLM KGW source bundle

`markllm/` contains an unmodified minimal source subset from
https://github.com/THU-BPM/MarkLLM/tree/0a4fe8c642b31b8a8c4993615b1c70a0c300d918
(Apache-2.0). Copyright headers and the full LICENSE are retained. README and
requirements are reference material, **not** an instruction to install the full
toolkit. `SHA256SUMS.json` records upstream file bytes. No algorithm changes.

The upstream root uses namespace packages and absolute `utils`, `exceptions`,
and `visualize` imports. The adapter adds this specific directory to sys.path
only when KGW is requested. No other toolkit algorithms are bundled.
`commit.txt` is our revision marker. The missing upstream watermark/__init__.py
is intentional (namespace package), not a missing download.
