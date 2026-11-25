"""Build a self-contained offline review page from an explicitly pinned private packet."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

from rag.index import ROOT
from rag.semantic_review import read_json, assess, template, new_output


def csp_hash(text):
    return base64.b64encode(hashlib.sha256(text.encode('utf-8')).digest()).decode('ascii')


def render(packet_path, packet_sha256, output):
    packet, observed = read_json(packet_path, packet_sha256)
    initial = template(packet, observed)
    assess(packet, observed, initial)  # Revalidate sources, passage bindings and scope before rendering.
    style = (ROOT / 'apps/web/generation-review.css').read_text(encoding='utf-8')
    module = (ROOT / 'apps/web/generation-review.mjs').read_text(encoding='utf-8')
    data = json.dumps({'packet': packet, 'initial': initial}, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c')
    script = module.replace('export function ', 'function ') + '\nconst data = ' + data + ';\nmountGenerationReview(document.getElementById("review"), data.packet, data.initial);\n'
    policy = f"default-src 'none'; script-src 'sha256-{csp_hash(script)}'; style-src 'sha256-{csp_hash(style)}'; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'"
    html = '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">' + \
        '<meta name="viewport" content="width=device-width,initial-scale=1">' + \
        f'<meta http-equiv="Content-Security-Policy" content="{policy}">' + \
        '<title>AIN | Generated answer review</title><style>' + style + '</style></head>' + \
        '<body><div id="review"></div><noscript>Enable JavaScript to review this packet locally.</noscript><script>' + script + '</script></body></html>\n'
    target = new_output(output)
    if target.suffix.lower() != '.html':
        raise ValueError('Use a fresh .html output under .local')
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(html)
    return {'page': str(target), 'page_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'packet_sha256': observed, 'network_required': False, 'human_ratings_supplied': False,
            'production_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', required=True)
    parser.add_argument('--packet-sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(render(args.packet, args.packet_sha256, args.output), indent=2))


if __name__ == '__main__':
    main()
