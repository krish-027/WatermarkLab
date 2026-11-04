"""Explicit download only: pinned GPT-2 assets; never called by the web API."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'openai-community/gpt2'
REVISION = '607a30d783dfa663caf39e06633721c8d4cfcd7e'
DEST = ROOT / '.cache' / 'kgw-gpt2'
EXPECTED = {
    'config.json': '0daed7749b4f02b8f76240d5444551d7b08712dab4d0adb8239c56ba823bb7b4',
    'tokenizer.json': '8414cab924d8b9b33013f0d221c5862f365ee9be39c5c2bfae8a5a9e970478a6',
    'tokenizer_config.json': '5e04eb606e3a1583530a42e36c2a6b6615c86f34fe77e44d9ddeb43ff940931f',
    'vocab.json': '196139668be63f3b5d6574427317ae82f612a97c5d1cdaf36ed2256dbf636783',
    'merges.txt': '1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5',
    'README.md': '0fcd631078093c2aa1d93438b898320b8a1167784e2a1ab37b8016e9de8b3c2e',
    'generation_config.json': 'ed0b32ac72c0f5f44a719abb2d7786ea5146c871f83717b7f2018065954de02b',
    'model.safetensors': '248dfc3911869ec493c76e65bf2fcf7f615828b0254c12b473182f0f81d3a707',
}

def verify_assets(names):
    hashes = {}
    for name in names:
        with (DEST / name).open('rb') as stream:
            hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
        if hashes[name] != EXPECTED[name]:
            raise RuntimeError(f'Pinned asset checksum mismatch: {name}; restore the exact revision before use.')
    return hashes

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-model', action='store_true', help='Also download ~548 MB safetensors for the independent generation spike')
    args = parser.parse_args()
    files = ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt', 'README.md', 'generation_config.json']
    if args.with_model:
        files += ['model.safetensors']
    DEST.mkdir(parents=True, exist_ok=True)
    for name in files:
        path = DEST / name
        if not path.exists():
            temporary = path.with_suffix(path.suffix + '.download')
            with urlopen(f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}', timeout=120) as response, temporary.open('wb') as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
            temporary.replace(path)
        print(f'{name}: {path.stat().st_size} bytes', flush=True)
    hashes = verify_assets(files)
    (DEST / 'asset_manifest.json').write_text(json.dumps({'model': MODEL, 'revision': REVISION, 'sha256': hashes}, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
