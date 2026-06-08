import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { SimulatedTradeService } from '../proxy/trading/simulated-trade.service';
import type { SimulatedTradeDto, StrategyProfileDto } from '../proxy/trading/dtos/models';
import { TradeStatus } from '../proxy/trading/trade-status.enum';
import { StrategyProfileService } from '../strategies/services/strategy-profile.service';
import { PaginatorComponent } from '../shared/components/paginator/paginator.component';

export interface AgentDecisionSnapshot {
  schema_version?: number;
  agent_version?: string;
  captured_at_utc?: string;
  agent_meta?: {
    entry_reason?: string;
    nexus_group?: string;
    tier?: string;
  };
  candidate?: Record<string, unknown>;
  position_sizing?: Record<string, unknown>;
}

export interface VersionStats {
  version: string;
  count: number;
  wins: number;
  losses: number;
  totalPnl: number;
}

@Component({
  selector: 'app-agent-trade-audit',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, PaginatorComponent],
  templateUrl: './agent-trade-audit.component.html',
  styleUrls: ['./agent-trade-audit.component.scss'],
})
export class AgentTradeAuditComponent implements OnInit {
  private readonly tradesApi = inject(SimulatedTradeService);
  private readonly strategyService = inject(StrategyProfileService);

  loading = signal(true);
  loadError = signal<string | null>(null);
  allRows = signal<SimulatedTradeDto[]>([]);
  selected = signal<SimulatedTradeDto | null>(null);
  showRawJson = signal(false);
  strategies = signal<StrategyProfileDto[]>([]);

  // Filtros
  strategyFilter = signal<string | null>(null);
  symbolFilter = signal<string | null>(null);
  statusFilter = signal<TradeStatus | null>(null);
  resultFilter = signal<'win' | 'loss' | null>(null);
  startDateFilter = signal<string | null>(null);
  endDateFilter = signal<string | null>(null);

  // Paginación
  currentPage = signal(1);
  pageSize = signal(10);
  totalItems = signal(0);
  pagedRows = signal<SimulatedTradeDto[]>([]);

  // Modal
  selectedForModal = signal<SimulatedTradeDto | null>(null);
  showRawJsonInModal = signal(false);

  // Descarga por estrategia
  downloadStrategyId = signal<string | null>(null);

  // Ordenamiento
  sortField = signal<string>('openedAt');
  sortDirection = signal<'asc' | 'desc'>('desc');

  readonly TradeStatus = TradeStatus;
  readonly Math = Math; // Expose Math to template for TP validation

  formatExitReason(reason: string): string {
    const map: Record<string, string> = {
      'tp_hit': '✅ TP Alcanzado',
      'sl_hit': '❌ SL Alcanzado',
      'btc_dump': '🔴 BTC Dump (salida preventiva)',
      'trailing_stop': '🟡 Trailing Stop (Cosecha)',
      'timeout': '⏱️ Timeout',
      'lse_exit': '🔵 LSE Exit',
      'regime_change': '🔄 Cambio de Régimen',
      'manual_profit': '💚 Cierre Manual (Profit)',
      'manual_loss': '🔴 Cierre Manual (Loss)',
      'unknown': '❓ Desconocido',
    };
    return map[reason] || reason;
  }

  parsedSelected = computed(() => this.parseSnapshot(this.selected()));

  /** Trades activos/históricos sin campo AgentDecisionJson en API (no aparecían antes al filtrar). */
  missingSnapshotCount = computed(
    () => this.allRows().filter(t => !this.hasAuditSnapshot(t)).length,
  );

  versionStats = computed(() => {
    const stats = new Map<string, VersionStats>();
    for (const t of this.allRows()) {
      const v = this.agentVersion(t);
      if (!stats.has(v)) {
        stats.set(v, { version: v, count: 0, wins: 0, losses: 0, totalPnl: 0 });
      }
      const s = stats.get(v)!;
      s.count++;
      if (t.status === TradeStatus.Win) s.wins++;
      if (t.status === TradeStatus.Loss) s.losses++;
      if (t.realizedPnl) s.totalPnl += t.realizedPnl;
    }
    return Array.from(stats.values()).sort((a, b) => b.version.localeCompare(a.version));
  });

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.loadError.set(null);
    forkJoin({
      active: this.tradesApi.getActiveTrades(),
      history: this.tradesApi.getTradeHistory(),
      strategies: this.strategyService.getAll(),
    }).subscribe({
      next: ({ active, history, strategies }) => {
        this.strategies.set(strategies || []);
        const seen = new Set<string>();
        const merged: SimulatedTradeDto[] = [];
        for (const t of [...(active ?? []), ...(history ?? [])]) {
          const id = String(t.id ?? '');
          if (!id || seen.has(id)) continue;
          seen.add(id);
          merged.push(t);
        }
        merged.sort((a, b) => {
          const ta = new Date(a.openedAt ?? 0).getTime();
          const tb = new Date(b.openedAt ?? 0).getTime();
          return tb - ta;
        });
        this.allRows.set(merged);
        this.applyFilters();
        this.loading.set(false);
      },
      error: err => {
        this.loading.set(false);
        this.loadError.set(err?.error?.error?.message || err?.message || 'No se pudo cargar el historial.');
      },
    });
  }

  applyFilters(): void {
    let filtered = [...this.allRows()];

    // Filtro por estrategia
    if (this.strategyFilter()) {
      filtered = filtered.filter(t => t.strategyProfileId === this.strategyFilter());
    }

    // Filtro por símbolo
    if (this.symbolFilter()) {
      const sym = this.symbolFilter()!.toUpperCase();
      filtered = filtered.filter(t => t.symbol?.toUpperCase().includes(sym));
    }

    // Filtro por estado
    if (this.statusFilter() !== null) {
      filtered = filtered.filter(t => t.status === this.statusFilter());
    }

    // Filtro por resultado
    if (this.resultFilter() === 'win') {
      filtered = filtered.filter(t => t.status === TradeStatus.Win);
    } else if (this.resultFilter() === 'loss') {
      filtered = filtered.filter(t => t.status === TradeStatus.Loss);
    }

    // Filtro por fecha inicio
    if (this.startDateFilter()) {
      const start = new Date(this.startDateFilter()!).getTime();
      filtered = filtered.filter(t => new Date(t.openedAt ?? 0).getTime() >= start);
    }

    // Filtro por fecha fin
    if (this.endDateFilter()) {
      const end = new Date(this.endDateFilter()!);
      end.setHours(23, 59, 59, 999);
      const endTime = end.getTime();
      filtered = filtered.filter(t => new Date(t.openedAt ?? 0).getTime() <= endTime);
    }

    // Ordenamiento
    const field = this.sortField();
    const dir = this.sortDirection() === 'asc' ? 1 : -1;
    filtered.sort((a, b) => {
      let valA: any;
      let valB: any;

      switch (field) {
        case 'openedAt':
          valA = new Date(a.openedAt ?? 0).getTime();
          valB = new Date(b.openedAt ?? 0).getTime();
          break;
        case 'symbol':
          valA = a.symbol?.toUpperCase() || '';
          valB = b.symbol?.toUpperCase() || '';
          break;
        case 'strategy':
          valA = this.getStrategyName(a);
          valB = this.getStrategyName(b);
          break;
        case 'pnl':
          valA = a.realizedPnl ?? 0;
          valB = b.realizedPnl ?? 0;
          break;
        default:
          valA = new Date(a.openedAt ?? 0).getTime();
          valB = new Date(b.openedAt ?? 0).getTime();
      }

      if (valA < valB) return -1 * dir;
      if (valA > valB) return 1 * dir;
      return 0;
    });

    // Actualizar total
    this.totalItems.set(filtered.length);

    // Paginación
    const start = (this.currentPage() - 1) * this.pageSize();
    const end = start + this.pageSize();
    this.pagedRows.set(filtered.slice(start, end));
  }

  clearFilters(): void {
    this.strategyFilter.set(null);
    this.symbolFilter.set(null);
    this.statusFilter.set(null);
    this.resultFilter.set(null);
    this.startDateFilter.set(null);
    this.endDateFilter.set(null);
    this.currentPage.set(1);
    this.applyFilters();
  }

  onPageChange(page: number): void {
    this.currentPage.set(page);
    this.applyFilters();
  }

  onPageSizeChange(size: number): void {
    this.pageSize.set(size);
    this.currentPage.set(1);
    this.applyFilters();
  }

  sortBy(field: string): void {
    if (this.sortField() === field) {
      this.sortDirection.set(this.sortDirection() === 'asc' ? 'desc' : 'asc');
    } else {
      this.sortField.set(field);
      this.sortDirection.set('desc');
    }
    this.currentPage.set(1);
    this.applyFilters();
  }

  openDetail(trade: SimulatedTradeDto): void {
    this.selectedForModal.set(trade);
    this.showRawJsonInModal.set(false);
  }

  closeModal(): void {
    this.selectedForModal.set(null);
    this.showRawJsonInModal.set(false);
  }

  /** Hay texto guardado por el agente al abrir (columna AgentDecisionJson). */
  hasAuditSnapshot(trade: SimulatedTradeDto | null | undefined): boolean {
    const raw = trade?.agentDecisionJson;
    return typeof raw === 'string' && raw.trim().length > 2;
  }

  parseSnapshot(trade: SimulatedTradeDto | null): AgentDecisionSnapshot | null {
    const raw = trade?.agentDecisionJson;
    if (!raw || typeof raw !== 'string') return null;
    try {
      return JSON.parse(raw) as AgentDecisionSnapshot;
    } catch {
      return null;
    }
  }

  pickRow(trade: SimulatedTradeDto): void {
    this.selected.set(trade);
    this.showRawJson.set(false);
  }

  signalSource(trade: SimulatedTradeDto): string {
    if (!this.hasAuditSnapshot(trade)) return '—';
    const snap = this.parseSnapshot(trade);
    const src = snap?.candidate?.['source'];
    return typeof src === 'string' ? this.mapSourceToLabel(src) : 'Nexus-15';
  }

  /** Maps internal agent source keys to human-readable tool names */
  mapSourceToLabel(src: string): string {
    const map: Record<string, string> = {
      'nexus_top':     'Nexus-15 Top',
      'nexus15_ui':    'Nexus-15',
      'nexus':         'Nexus-15',
      'nexus5_bridge': 'Nexus-5',
      'redis_bridge':  'Nexus-15',  // bridge signals are confirmed by Nexus-15
      'LSE':           'LSE',
      'lse':           'LSE',
    };
    return map[src] ?? src;
  }

  getStrategyName(trade: SimulatedTradeDto): string {
    const id = trade.strategyProfileId;
    if (!id || id === '00000000-0000-0000-0000-000000000000') {
      return 'Standard Scalping';
    }
    const found = this.strategies().find(s => s.id === id);
    return found?.name || 'Unknown Strategy';
  }

  agentVersion(trade: SimulatedTradeDto): string {
    if (!this.hasAuditSnapshot(trade)) return 'v1.0';
    const snap = this.parseSnapshot(trade);
    return snap?.agent_version || 'v1.0';
  }

  scoreSummary(trade: SimulatedTradeDto): string {
    if (!this.hasAuditSnapshot(trade)) return '—';
    const snap = this.parseSnapshot(trade);
    const c = snap?.candidate;
    if (!c) return '—';
    if (c['source'] === 'LSE') {
      const s = c['lse_score'] ?? c['confluence_score'];
      return typeof s === 'number' ? `LSE ${s.toFixed(1)}` : 'LSE';
    }
    const conf = c['confluence_score'];
    const nx = c['nexus_confidence'];
    const scar = c['scar_score'];
    const parts: string[] = [];
    if (typeof conf === 'number') parts.push(`Conf ${conf.toFixed(0)}`);
    if (typeof nx === 'number') parts.push(`Nx ${nx}%`);
    if (typeof scar === 'number') parts.push(`SCAR ${scar}`);
    return parts.length ? parts.join(' · ') : '—';
  }

  statusLabel(s?: TradeStatus): string {
    if (s === TradeStatus.Open) return 'Abierta';
    if (s === TradeStatus.Win) return 'Win';
    if (s === TradeStatus.Loss) return 'Loss';
    if (s === undefined || s === null) return '—';
    return String(s);
  }

  groupScoreEntries(gs: unknown): { key: string; val: number }[] {
    if (!gs || typeof gs !== 'object') return [];
    return Object.entries(gs as Record<string, number>)
      .filter(([, v]) => typeof v === 'number')
      .map(([key, val]) => ({ key, val }));
  }

  /** Etiqueta corta para barras de grupos (misma familia visual que ya te gustaba). */
  groupScoreLabel(key: string): string {
    const m: Record<string, string> = {
      g1_price_action: 'G1 · Price action',
      g2_smc_ict: 'G2 · SMC / ICT',
      g3_wyckoff: 'G3 · Wyckoff',
      g4_fractals: 'G4 · Fractales',
      g5_volume: 'G5 · Volumen',
      g6_ml: 'G6 · ML',
    };
    return m[key] ?? this.humanizeKey(key);
  }

  private readonly positionSizingKeyLabels: Record<string, string> = {
    symbol: 'Símbolo',
    side: 'Lado',
    margin: 'Margen',
    leverage: 'Apalancamiento',
    entry_price: 'Precio entrada',
    tp_price: 'Take profit',
    sl_price: 'Stop loss',
    range_pct_used: 'Rango % usado',
  };

  private readonly positionSizingOrder = [
    'symbol',
    'side',
    'margin',
    'leverage',
    'entry_price',
    'tp_price',
    'sl_price',
    'range_pct_used',
  ] as const;

  positionSizingRows(ps: Record<string, unknown>): { label: string; value: string }[] {
    const rows: { label: string; value: string }[] = [];
    for (const k of this.positionSizingOrder) {
      if (!(k in ps)) continue;
      rows.push({
        label: this.positionSizingKeyLabels[k] ?? this.humanizeKey(k),
        value: this.formatPositionSizingValue(k, ps[k]),
      });
    }
    const rest = Object.keys(ps)
      .filter(k => !this.positionSizingOrder.includes(k as (typeof this.positionSizingOrder)[number]))
      .sort();
    for (const k of rest) {
      rows.push({
        label: this.positionSizingKeyLabels[k] ?? this.humanizeKey(k),
        value: this.formatScalarForDisplay(ps[k]),
      });
    }
    return rows;
  }

  private formatPositionSizingValue(key: string, v: unknown): string {
    if (key === 'side') {
      if (v === 0 || v === '0') return 'Long';
      if (v === 1 || v === '1') return 'Short';
    }
    if (typeof v === 'number' && (key.includes('price') || key === 'margin')) {
      return v.toLocaleString('es-AR', { maximumFractionDigits: 8 });
    }
    return this.formatScalarForDisplay(v);
  }

  /** Campos escalares de la respuesta Nexus (sin blobs JSON). */
  nexusSummaryItems(nx: Record<string, unknown>): { label: string; value: string }[] {
    const items: { label: string; value: string }[] = [];
    const push = (label: string, v: unknown, fmt?: (x: unknown) => string) => {
      if (v === undefined || v === null || v === '') return;
      items.push({ label, value: fmt ? fmt(v) : this.formatScalarForDisplay(v) });
    };
    push('Símbolo', nx['symbol']);
    push('Marco temporal', nx['timeframe']);
    const at = nx['analyzed_at'] ?? nx['analysis_id'];
    if (typeof at === 'string') {
      items.push({ label: 'Analizado (UTC)', value: this.tryFormatIsoDate(at) });
    }
    push('Recomendación', nx['recommendation']);
    push('Dirección (API)', nx['direction']);
    push('Régimen (API)', nx['regime']);
    if (typeof nx['volume_explosion'] === 'boolean') {
      items.push({ label: 'Explosión de volumen', value: nx['volume_explosion'] ? 'Sí' : 'No' });
    }
    if (typeof nx['ai_confidence'] === 'number') {
      items.push({ label: 'Confianza IA (respuesta)', value: `${nx['ai_confidence']}%` });
    }
    if (typeof nx['estimated_range_percent'] === 'number') {
      items.push({
        label: 'Rango est. % (respuesta)',
        value: `${nx['estimated_range_percent']}`,
      });
    }
    return items;
  }

  nexusProbBars(nx: Record<string, unknown>): { label: string; val: number }[] {
    const defs: [string, string][] = [
      ['next_5_candles_prob', 'Próx. 5 velas'],
      ['next_15_candles_prob', 'Próx. 15 velas'],
      ['next_20_candles_prob', 'Próx. 20 velas'],
    ];
    return defs
      .map(([key, label]) => {
        const v = nx[key];
        if (typeof v !== 'number') return null;
        const pct = v <= 1 ? v * 100 : v;
        return { label, val: Math.min(100, Math.max(0, pct)) };
      })
      .filter((x): x is NonNullable<typeof x> => x != null);
  }

  detectivityCards(det: unknown): { id: string; title: string; body: string }[] {
    const rec = this.asRecord(det);
    if (!rec) return [];
    const order = [
      'g1_price_action',
      'g2_smc_ict',
      'g3_wyckoff',
      'g4_fractals',
      'g5_volume',
      'g6_ml',
    ];
    const titles: Record<string, string> = {
      g1_price_action: 'Price action',
      g2_smc_ict: 'SMC / ICT',
      g3_wyckoff: 'Wyckoff',
      g4_fractals: 'Fractales / estructura',
      g5_volume: 'Volumen / CVD',
      g6_ml: 'ML / indicadores',
    };
    const out: { id: string; title: string; body: string }[] = [];
    for (const k of order) {
      const v = rec[k];
      if (v === undefined || v === null) continue;
      out.push({
        id: k,
        title: titles[k] ?? this.humanizeKey(k),
        body: typeof v === 'string' ? v : this.formatScalarForDisplay(v),
      });
    }
    for (const [k, v] of Object.entries(rec)) {
      if (order.includes(k)) continue;
      out.push({
        id: k,
        title: this.humanizeKey(k),
        body: typeof v === 'object' ? this.safeJson(v) : String(v),
      });
    }
    return out;
  }

  featureGridRows(feats: unknown): { label: string; value: string }[] {
    const rec = this.asRecord(feats);
    if (!rec) return [];
    return Object.keys(rec)
      .sort()
      .map(key => ({
        label: this.humanizeKey(key),
        value: this.formatFeatureValue(rec[key]),
      }));
  }

  shouldShowNxGroupScores(
    candidateGs: unknown,
    nx: Record<string, unknown>,
  ): { show: boolean; source: Record<string, unknown> | null } {
    if (this.groupScoreEntries(candidateGs).length > 0) {
      return { show: false, source: null };
    }
    const gs = nx['group_scores'];
    const rec = this.asRecord(gs);
    if (rec && this.groupScoreEntries(rec).length > 0) {
      return { show: true, source: rec };
    }
    return { show: false, source: null };
  }

  humanizeKey(key: string): string {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());
  }

  private tryFormatIsoDate(iso: string): string {
    const d = Date.parse(iso);
    if (Number.isNaN(d)) return iso;
    return new Date(d).toLocaleString('es-AR');
  }

  private formatScalarForDisplay(v: unknown): string {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'boolean') return v ? 'Sí' : 'No';
    if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(v);
    return String(v);
  }

  private formatFeatureValue(v: unknown): string {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'boolean') return v ? 'Sí' : 'No';
    if (typeof v === 'number') {
      if (Number.isInteger(v)) return String(v);
      const r = Math.round(v * 10000) / 10000;
      return String(r);
    }
    return String(v);
  }

  private safeJson(v: unknown): string {
    try {
      return JSON.stringify(v, null, 2);
    } catch {
      return String(v);
    }
  }

  reasonLines(c?: Record<string, unknown>): string[] {
    const r = c?.['reasons'];
    return Array.isArray(r) ? r.map(x => String(x)) : [];
  }

  asRecord(o: unknown): Record<string, unknown> | null {
    if (o && typeof o === 'object' && !Array.isArray(o)) return o as Record<string, unknown>;
    return null;
  }

  /** Evita "[object Object]" al interpolar valores del snapshot en plantillas keyvalue. */
  auditIsNested(v: unknown): boolean {
    return v !== null && typeof v === 'object';
  }

  auditDisplay(v: unknown): string {
    if (v === null || v === undefined) return '—';
    const t = typeof v;
    if (t === 'string' || t === 'number' || t === 'boolean') return String(v);
    try {
      return JSON.stringify(v, null, 2);
    } catch {
      return String(v);
    }
  }

  /** Pares legibles para SCAR / LSE cuando hay pocos campos (evita lista tipo JSON). */
  auditRecordRows(rec: Record<string, unknown>): { label: string; value: string }[] {
    return Object.keys(rec)
      .sort()
      .map(k => ({
        label: this.humanizeKey(k),
        value: this.auditIsNested(rec[k]) ? this.safeJson(rec[k]) : this.formatScalarForDisplay(rec[k]),
      }));
  }

  downloadAll(): void {
    let out = '';
    
    for (const tr of this.allRows()) {
      const pnlStr = (tr.realizedPnl != null && tr.status !== TradeStatus.Open) 
        ? tr.realizedPnl.toLocaleString('es-AR', { maximumFractionDigits: 2 }) 
        : '—';
      
      const openedStr = tr.openedAt ? new Date(tr.openedAt).toLocaleString('es-AR') : '—';
      const closedStr = tr.closedAt ? new Date(tr.closedAt).toLocaleString('es-AR') : '—';
      const hasAudit = this.hasAuditSnapshot(tr) ? 'Sí' : 'No';
      const strategyName = this.getStrategyName(tr);
      
      out += `${tr.symbol}\t${strategyName}\t${hasAudit}\t${this.signalSource(tr)}\t${this.scoreSummary(tr)}\t${this.statusLabel(tr.status)}\t${openedStr}\t${closedStr}\t${pnlStr}\n`;
      out += `${tr.symbol}\n`;
      out += `Estrategia: ${strategyName}\n`;
      out += `${this.signalSource(tr)}\n`;
      out += `Ejecución simulada\n`;
      out += `Entrada (servidor)\n${tr.entryPrice}\n`;
      out += `TP\n${tr.tpPrice}\n`;
      out += `SL\n${tr.slPrice}\n`;
      out += `Margen / Lev\n${tr.margin} USDT × ${tr.leverage}\n`;
      
      const snap = this.parseSnapshot(tr);
      if (snap) {
        const ps = this.asRecord(snap.position_sizing);
        if (ps) {
          out += `Tamaño (motor de riesgo)\n`;
          for (const row of this.positionSizingRows(ps)) {
            out += `${row.label}\n${row.value}\n`;
          }
        }
        
        if (snap.agent_meta) {
          out += `Razonamiento del agente\n${snap.agent_meta.entry_reason || ''}\n\n`;
          out += `Grupo Nexus\n${snap.agent_meta.nexus_group || ''}\n`;
          out += `Tier\n${snap.agent_meta.tier || ''}\n`;
          out += `Capturado\n${snap.captured_at_utc ? new Date(snap.captured_at_utc).toLocaleString('es-AR') : ''}\n`;
        }
        
        const c = snap.candidate;
        if (c) {
          out += `Nexus-15 · lectura al ejecutar\n`;
          out += `Confianza IA\n${c['nexus_confidence'] ?? ''}\n`;
          out += `Dirección\n${c['nexus_direction'] ?? ''}\n`;
          out += `Régimen\n${c['regime'] ?? ''}\n`;
          out += `Rango est. %\n${c['estimated_range_pct'] ?? ''}\n`;
          out += `Confluencia\n${c['confluence_score'] ?? ''}\n`;
          
          const audit = this.asRecord(c['agent_audit_context']);
          if (audit) {
            const nx = this.asRecord(audit['nexus15']);
            if (nx) {
              out += `Respuesta Nexus (API)\n`;
              for (const item of this.nexusSummaryItems(nx)) {
                out += `${item.label}\n${item.value}\n`;
              }
            }
          }
          
          out += `SCAR\nscore_grial en candidato: ${c['scar_score'] ?? ''}\n\n`;
          
          if (c['source'] === 'LSE') {
            out += `Liquidity Engine (LSE)\n`;
            out += `Score LSE\n${c['lse_score'] ?? ''}\n`;
            out += `Detección\n${c['lse_detection_mode'] ?? ''}\n`;
            out += `Entry modelo\n${c['lse_entry_price'] ?? ''}\n`;
            out += `SL modelo\n${c['lse_stop_loss'] ?? ''}\n`;
            out += `TP1 modelo\n${c['lse_take_profit_1'] ?? ''}\n`;
            
            if (audit) {
              const lseSig = this.asRecord(audit['lse_signal']);
              if (lseSig) {
                out += `Señal LSE\n`;
                for (const row of this.auditRecordRows(lseSig)) {
                  out += `${row.label}\n${row.value}\n`;
                }
              }
            }
          }
          
          if (this.reasonLines(c).length > 0) {
             out += `Reasoning\n`;
             out += JSON.stringify(this.reasonLines(c)) + '\n';
          }
        }
      }
      
      out += `\n--------------------------------------------------\n\n`;
    }
    
    const blob = new Blob([out], { type: 'text/plain;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `agent_audit_history_${new Date().toISOString().replace(/[:.]/g, '-')}.txt`;
    a.click();
    window.URL.revokeObjectURL(url);
  }

  downloadCsv(): void {
    // Semicolon is better for Excel in Spanish locales, and we add BOM for UTF-8 characters
    let out = '\uFEFF'; 
    out += 'Symbol;Apertura;Cierre;Source;Strategy;NexusConf;Confluence;LSE_Score;SCAR;Estado;RealizedPnL;Margin;Leverage;EntryReason\n';
    
    for (const tr of this.allRows()) {
      const pnlStr = (tr.realizedPnl != null && tr.status !== TradeStatus.Open) ? tr.realizedPnl.toFixed(2).replace('.', ',') : '';
      const openedStr = tr.openedAt ? new Date(tr.openedAt).toLocaleString('es-AR') : '';
      const closedStr = tr.closedAt ? new Date(tr.closedAt).toLocaleString('es-AR') : '';
      
      const snap = this.parseSnapshot(tr);
      let nxConf = '';
      let conf = '';
      let lseScore = '';
      let scar = '';
      let reason = '';
      let src = this.signalSource(tr);
      let strat = this.getStrategyName(tr);
      
      if (snap) {
         if (snap.agent_meta) {
           reason = `"${(snap.agent_meta.entry_reason || '').replace(/"/g, '""')}"`;
         }
         if (snap.candidate) {
           const c = snap.candidate;
           nxConf = String(c['nexus_confidence'] ?? '').replace('.', ',');
           conf = String(c['confluence_score'] ?? '').replace('.', ',');
           lseScore = String(c['lse_score'] ?? '').replace('.', ',');
           scar = String(c['scar_score'] ?? '').replace('.', ',');
         }
      }
      
      // We use ; as separator for Spanish Excel
      out += `${tr.symbol};${openedStr};${closedStr};${src};${strat};${nxConf};${conf};${lseScore};${scar};${this.statusLabel(tr.status)};${pnlStr};${tr.margin};${tr.leverage};${reason}\n`;
    }
    
    const blob = new Blob([out], { type: 'text/csv;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `agent_audit_history_${new Date().toISOString().replace(/[:.]/g, '-')}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  }

  downloadFilteredStrategyTxt(): void {
    const strategyId = this.downloadStrategyId();
    if (!strategyId) return;

    // Filtrar trades por estrategia seleccionada
    const filteredTrades = this.allRows().filter(t => t.strategyProfileId === strategyId);
    
    if (filteredTrades.length === 0) {
      alert('No hay trades para esta estrategia');
      return;
    }

    const strategyName = this.strategies().find(s => s.id === strategyId)?.name || 'Unknown';
    
    let out = '';
    
    for (const tr of filteredTrades) {
      const pnlStr = (tr.realizedPnl != null && tr.status !== TradeStatus.Open) 
        ? tr.realizedPnl.toLocaleString('es-AR', { maximumFractionDigits: 2 }) 
        : '—';
      
      const openedStr = tr.openedAt ? new Date(tr.openedAt).toLocaleString('es-AR') : '—';
      const closedStr = tr.closedAt ? new Date(tr.closedAt).toLocaleString('es-AR') : '—';
      const hasAudit = this.hasAuditSnapshot(tr) ? 'Sí' : 'No';
      
      out += `${tr.symbol}\n`;
      out += `Estrategia: ${strategyName}\n`;
      out += `${this.signalSource(tr)}\n`;
      out += `Ejecución simulada\n`;
      out += `Entrada (servidor)\n${tr.entryPrice}\n`;
      out += `TP\n${tr.tpPrice}\n`;
      out += `SL\n${tr.slPrice}\n`;
      out += `Margen / Lev\n${tr.margin} USDT × ${tr.leverage}\n`;
      
      const snap = this.parseSnapshot(tr);
      if (snap) {
        const ps = this.asRecord(snap.position_sizing);
        if (ps) {
          out += `Tamaño (motor de riesgo)\n`;
          for (const row of this.positionSizingRows(ps)) {
            out += `${row.label}\n${row.value}\n`;
          }
        }
        
        if (snap.agent_meta) {
          out += `Razonamiento del agente\n${snap.agent_meta.entry_reason || ''}\n\n`;
          out += `Grupo Nexus\n${snap.agent_meta.nexus_group || ''}\n`;
          out += `Tier\n${snap.agent_meta.tier || ''}\n`;
          out += `Capturado\n${snap.captured_at_utc ? new Date(snap.captured_at_utc).toLocaleString('es-AR') : ''}\n`;
        }
        
        const c = snap.candidate;
        if (c) {
          out += `Nexus-15 · lectura al ejecutar\n`;
          out += `Confianza IA\n${c['nexus_confidence'] ?? ''}\n`;
          out += `Dirección\n${c['nexus_direction'] ?? ''}\n`;
          out += `Régimen\n${c['regime'] ?? ''}\n`;
          out += `Rango est. %\n${c['estimated_range_pct'] ?? ''}\n`;
          out += `Confluencia\n${c['confluence_score'] ?? ''}\n`;
          
          const audit = this.asRecord(c['agent_audit_context']);
          if (audit) {
            const nx = this.asRecord(audit['nexus15']);
            if (nx) {
              out += `Respuesta Nexus (API)\n`;
              for (const item of this.nexusSummaryItems(nx)) {
                out += `${item.label}\n${item.value}\n`;
              }
            }
          }
          
          out += `SCAR\nscore_grial en candidato: ${c['scar_score'] ?? ''}\n\n`;
          
          if (c['source'] === 'LSE') {
            out += `Liquidity Engine (LSE)\n`;
            out += `Score LSE\n${c['lse_score'] ?? ''}\n`;
            out += `Detección\n${c['lse_detection_mode'] ?? ''}\n`;
            out += `Entry modelo\n${c['lse_entry_price'] ?? ''}\n`;
            out += `SL modelo\n${c['lse_stop_loss'] ?? ''}\n`;
            out += `TP1 modelo\n${c['lse_take_profit_1'] ?? ''}\n`;
            
            if (audit) {
              const lseSig = this.asRecord(audit['lse_signal']);
              if (lseSig) {
                out += `Señal LSE\n`;
                for (const row of this.auditRecordRows(lseSig)) {
                  out += `${row.label}\n${row.value}\n`;
                }
              }
            }
          }
          
          if (this.reasonLines(c).length > 0) {
             out += `Reasoning\n`;
             out += JSON.stringify(this.reasonLines(c)) + '\n';
          }
        }
      }
      
      out += `\n--------------------------------------------------\n\n`;
    }
    
    const blob = new Blob([out], { type: 'text/plain;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit_${strategyName.replace(/\s+/g, '_')}_${new Date().toISOString().replace(/[:.]/g, '-')}.txt`;
    a.click();
    window.URL.revokeObjectURL(url);
  }
}
