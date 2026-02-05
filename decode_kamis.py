import os
import httpx
import json
import pprint

key = os.environ.get('KAMIS_API_KEY', '').strip()
cert = os.environ.get('KAMIS_CERT_ID', '').strip() or 'meat-a-eye'
params = {
    'action': 'productInfo',
    'p_cert_key': key,
    'p_cert_id': cert,
    'p_returntype': 'json',
}
resp = httpx.get('https://www.kamis.or.kr/service/price/xml.do', params=params, timeout=10)
data = json.loads(resp.content.decode('utf-8', 'ignore'))

def fix_str(value: str) -> str:
    try:
        return value.encode('latin1').decode('cp949')
    except Exception:
        return value

fixed = []
for item in data.get('info', []):
    fixed.append({k: fix_str(v) if isinstance(v, str) else v for k, v in item.items()})

beef = [item for item in fixed if item.get('itemcode') == '4301']
print('beef count:', len(beef))
pprint.pp(beef[:20])
