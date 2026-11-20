"""Explicit ingestion of a fixed allowlist of public project evidence documents."""
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone
import numpy as np
from rag import ollama

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / '.local/knowledge/index.json'
SOURCES = ('docs/DELAY_V2.md', 'docs/DELAY_BASELINE.md', 'docs/DATA_INGESTION.md',
           'docs/MODEL_DATASET.md', 'docs/GATE_OPTIMIZATION.md', 'docs/LOCAL_IDENTITY.md')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def chunks_for(path, text):
    rows, group, start, heading = [], [], 1, path
    def flush():
        if group and any(line.strip() for line in group):
            content = '\n'.join(group)
            rows.append({'id': digest(f'{path}:{start}:{content}'.encode())[:20], 'source': path,
                'heading': heading, 'start_line': start, 'end_line': start + len(group) - 1, 'text': content})
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith('#') or (sum(map(len, group)) + len(line) > 1300 and group):
            flush(); group = []; start = number
            if line.startswith('#'):
                heading = line.lstrip('#').strip()
        group.append(line)
    flush()
    return rows


def validate_vectors(values, count):
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != count or matrix.shape[1] != 768 or not np.isfinite(matrix).all():
        raise RuntimeError('Invalid embedding matrix')
    norms = np.linalg.norm(matrix, axis=1)
    if (norms < 1e-8).any():
        raise RuntimeError('Empty embedding vector')
    return matrix / norms[:, None]


def build():
    installed = ollama.models()
    if ollama.EMBED_MODEL not in installed:
        raise RuntimeError('Required local embedding model is missing')
    chunks, sources = [], []
    for source in SOURCES:
        raw = (ROOT / source).read_bytes()
        if len(raw) > 100_000:
            raise RuntimeError('Source exceeds ingestion bound')
        sources.append({'path': source, 'sha256': digest(raw)})
        chunks.extend(chunks_for(source, raw.decode('utf-8')))
    embeddings = []
    for offset in range(0, len(chunks), 8):
        batch = chunks[offset:offset + 8]
        embeddings.extend(ollama.embed([c['heading'] + '\n' + c['text'] for c in batch]))
    matrix = validate_vectors(embeddings, len(chunks))
    revision = subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    payload = {'version': 1, 'created_at': datetime.now(timezone.utc).isoformat(), 'revision': revision,
        'embedding_model': ollama.EMBED_MODEL, 'embedding_digest': installed[ollama.EMBED_MODEL],
        'sources': sources, 'chunks': chunks, 'vectors': matrix.tolist()}
    canonical = json.dumps(payload, sort_keys=True).encode()
    envelope = {'sha256': digest(canonical), 'payload': payload}
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    temporary = INDEX.with_suffix('.tmp')
    temporary.write_text(json.dumps(envelope), encoding='utf-8')
    temporary.replace(INDEX)
    return {'sources': len(sources), 'chunks': len(chunks), 'dimensions': matrix.shape[1], 'index_sha256': envelope['sha256']}


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
