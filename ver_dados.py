import json
from pathlib import Path

DADOS = Path(r"C:\Users\kelly\OneDrive\Documentos\Claude\Gestão de incidentes\dados-reais.json")
with open(DADOS, encoding="utf-8-sig") as f:
    d = json.load(f)

print(f"Total: {len(d)} registros\n")
for r in d[:20]:
    subj  = r.get("subject", "")
    resp  = r.get("artiaResp", "")
    categ = r.get("category", "")
    print(f"{resp:<30} | {categ:<20} | {subj}")
