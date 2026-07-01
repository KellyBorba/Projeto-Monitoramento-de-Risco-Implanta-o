/**
 * hubspot-only-sync.js — Busca tickets do HubSpot e salva dados-reais.json
 *
 * Não depende do Artia. Busca todos os tickets com suas propriedades
 * e resolve o nome do analista N1 via Owners API.
 *
 * Executar:
 *   node hubspot-only-sync.js
 *   node hubspot-only-sync.js --dias=90   ← tickets dos últimos N dias
 */

require('dotenv').config();
const axios = require('axios');
const fs    = require('fs');

// Período: 01/01/2026 até ontem (D-1) — atualiza automaticamente mês a mês
const DATA_INICIO = new Date('2026-01-01T00:00:00Z');
const _ontem = new Date();
_ontem.setDate(_ontem.getDate() - 1);
_ontem.setHours(23, 59, 59, 999);
const DATA_FIM = _ontem;

const HUB_HEADERS = {
  Authorization:  `Bearer ${process.env.HUBSPOT_TOKEN}`,
  'Content-Type': 'application/json',
};

// ─── Owners HubSpot (ID → nome) ───────────────────────────────────────────────
async function carregarOwners() {
  const res = await axios.get(
    'https://api.hubapi.com/crm/v3/owners?limit=100',
    { headers: HUB_HEADERS }
  );
  const mapa = {};
  (res.data.results || []).forEach(o => {
    mapa[o.id] = `${o.firstName || ''} ${o.lastName || ''}`.trim() || o.email || 'Analista inativo';
  });
  console.log(`  ${Object.keys(mapa).length} analistas carregados.`);
  return mapa;
}

// ─── Buscar tickets de um intervalo ──────────────────────────────────────────
async function buscarPeriodo(inicio, fim) {
  const properties = [
    'subject', 'content', 'hs_ticket_category', 'hs_ticket_priority',
    'hs_pipeline_stage', 'createdate', 'closed_date', 'hubspot_owner_id',
  ];

  let tickets = [], after;
  do {
    const body = {
      filterGroups: [{
        filters: [
          { propertyName: 'createdate', operator: 'GTE', value: String(inicio.getTime()) },
          { propertyName: 'createdate', operator: 'LTE', value: String(fim.getTime()) },
        ],
      }],
      properties,
      limit: 100,
      sorts: [{ propertyName: 'createdate', direction: 'ASCENDING' }],
      ...(after ? { after } : {}),
    };

    const res = await axios.post(
      'https://api.hubapi.com/crm/v3/objects/tickets/search',
      body,
      { headers: HUB_HEADERS }
    );

    tickets = tickets.concat(res.data.results || []);
    after   = res.data.paging?.next?.after;
  } while (after);

  return tickets;
}

// ─── Buscar mês a mês (evita limite de 10.000) ───────────────────────────────
async function buscarTickets() {
  let todos = [];
  let cursor = new Date(DATA_INICIO);

  while (cursor < DATA_FIM) {
    const fimMes = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0, 23, 59, 59, 999);
    const ate    = fimMes < DATA_FIM ? fimMes : DATA_FIM;

    const label = cursor.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
    process.stdout.write(`  Buscando ${label}...`);

    const lote = await buscarPeriodo(cursor, ate);
    process.stdout.write(` ${lote.length} tickets\n`);
    todos = todos.concat(lote);

    // avança para o próximo mês
    cursor = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
  }

  // Remove duplicatas por ID
  const vistos = new Set();
  return todos.filter(t => { if (vistos.has(t.id)) return false; vistos.add(t.id); return true; });
}

// ─── Pipeline stages ──────────────────────────────────────────────────────────
const STAGES_FECHADOS = new Set([
  '151512326','1301981612','1276861825','151781184','151382299',
  '151382300','151550800','151550801',
]);

// ─── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  console.log('\n🔄 Buscando tickets do HubSpot...');
  console.log(`   Período: ${DATA_INICIO.toLocaleDateString('pt-BR')} até ${DATA_FIM.toLocaleDateString('pt-BR')}\n`);

  if (!process.env.HUBSPOT_TOKEN) {
    console.error('❌ HUBSPOT_TOKEN não encontrado no .env');
    process.exit(1);
  }

  console.log('🔄 Carregando analistas...');
  const ownerMap = await carregarOwners();

  console.log('🔄 Buscando tickets...');
  const tickets = await buscarTickets();
  console.log(`   ${tickets.length} tickets encontrados.\n`);

  const registros = tickets.map(t => {
    const p       = t.properties;
    const ownerId = p.hubspot_owner_id || null;
    const fechado = STAGES_FECHADOS.has(p.hs_pipeline_stage);

    return {
      hubId:     t.id,
      subject:   p.subject    || '(sem título)',
      content:   p.content    || '',
      category:  p.hs_ticket_category || '',
      priority:  p.hs_ticket_priority || '',
      hubClosed: fechado,
      createdate: p.createdate  || null,
      closedDate: p.closed_date || null,
      hubOwner:  ownerId ? (ownerMap[ownerId] || `ID ${ownerId}`) : null,
      artiaTitle: null,
      artiaStatus: null,
      artiaClosed: null,
      artiaResp:   null,
      artiaEnd:    null,
    };
  });

  const saida = 'dados-reais.json';
  fs.writeFileSync(saida, JSON.stringify(registros, null, 2), 'utf8');
  console.log(`✅ ${saida} gerado com ${registros.length} tickets.`);

  // Resumo
  const abertos  = registros.filter(r => !r.hubClosed).length;
  const alta     = registros.filter(r => r.priority === 'HIGH').length;
  const semOwner = registros.filter(r => !r.hubOwner).length;
  console.log(`\n📊 Resumo:`);
  console.log(`   Abertos:        ${abertos}`);
  console.log(`   Alta prioridade:${alta}`);
  console.log(`   Sem analista:   ${semOwner}`);
  console.log(`\n🚀 Recarregue o dashboard para ver os dados atualizados.`);
}

main().catch(err => {
  console.error('\n❌ Erro:', err.response?.data || err.message);
  process.exit(1);
});
