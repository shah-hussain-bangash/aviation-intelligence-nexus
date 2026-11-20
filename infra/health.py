"""Container database readiness probe, distinct from production qualification."""
import json
from urllib.request import urlopen


if __name__=='__main__':
    with urlopen('http://127.0.0.1:8002/health/ready',timeout=3) as response:
        if response.status!=200 or json.load(response).get('status')!='ready':raise SystemExit(1)
