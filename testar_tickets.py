import sys
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

import os
from hubspot import HubSpot

client = HubSpot(access_token=os.getenv('HUBSPOT_API_KEY'))

# Busca os 10 tickets mais recentes
resp = client.crm.tickets.basic_api.get_page(
    limit=10,
    properties=['subject', 'createdate', 'hs_pipeline_stage']
)

print(f'Total de tickets encontrados: {len(resp.results)}')
for t in resp.results:
    assunto = t.properties.get('subject') or 'sem titulo'
    data    = t.properties.get('createdate') or ''
    print(f'  [{t.id}] {assunto[:60]} — {data[:10]}')
