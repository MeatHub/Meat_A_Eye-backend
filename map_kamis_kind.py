import os
import httpx
import xmltodict

key = os.environ.get('KAMIS_API_KEY', '').strip()
cert = os.environ.get('KAMIS_CERT_ID', '').strip() or 'meat-a-eye'
base = 'https://www.kamis.or.kr/service/price/xml.do'

for kind in [f'{i:02d}' for i in range(21, 61)]:
    params = {
        'action': 'periodProductList',
        'p_cert_key': key,
        'p_cert_id': cert,
        'p_returntype': 'xml',
        'p_startday': '2026-01-28',
        'p_endday': '2026-02-03',
        'p_productclscode': '01',
        'p_itemcategorycode': '500',
        'p_itemcode': '4301',
        'p_kindcode': kind,
        'p_productrankcode': '',
        'p_countrycode': '',
        'p_convert_kg_yn': 'N',
    }
    resp = httpx.get(base, params=params, timeout=10)
    if resp.status_code != 200:
        continue
    data = xmltodict.parse(resp.text)
    error_code = data.get('document', {}).get('data', {}).get('error_code')
    if error_code and error_code != '000':
        continue
    items = data.get('document', {}).get('data', {}).get('item')
    if not items:
        continue
    if isinstance(items, list):
        sample = items[0]
    else:
        sample = items
    name = sample.get('item_name') or sample.get('productName') or sample.get('itemName')
    if name:
        print(kind, name)
