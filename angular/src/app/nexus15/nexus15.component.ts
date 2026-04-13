import { Component, OnInit, OnDestroy, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { Nexus15Service } from '../proxy/trading/nexus15/nexus15.service';
import { Nexus15ResultDto } from '../proxy/trading/nexus15/models';
import { TradingSignalrService } from '../services/trading-signalr.service';

@Component({
  selector: 'app-nexus15',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './nexus15.component.html',
  styleUrls: ['./nexus15.component.scss'],
})
export class Nexus15Component implements OnInit, OnDestroy {
  private nexus15Service = inject(Nexus15Service);
  private signalR = inject(TradingSignalrService);

  // ── State ──────────────────────────────────────────────────────────────
  selectedSymbol = signal('BTCUSDT');
  isLoading = signal(false);
  data = signal<Nexus15ResultDto | null>(null);
  errorMsg = signal<string | null>(null);
  terminalLines = signal<string[]>([]);
  scanCount = signal(0);

  private sub?: Subscription;
  private terminalInterval?: any;
  private terminalMessages = [
    'NEXUS-15 ONLINE...',
    'CONNECTING TO REDIS PIPELINE...',
    'LOADING XGB MODEL V1...',
    'FEATURE ENGINE READY [20 FEATURES]',
    'WYCKOFF ENGINE INITIALIZED',
    'SMC/ICT MODULE LOADED',
    'PRICE ACTION LAYER ACTIVE',
    'VOLUME PROFILE SCANNING...',
    'FRACTAL STRUCTURE MAP [OK]',
    'ML PREDICTOR CALIBRATED',
    'AWAITING 15M CANDLE CLOSE...',
    'SIGNAL ROUTER CONNECTED',
    'BINANCE FEED ACTIVE',
    'SEMAPHORE(3,3) SECURED',
    'NEXUS-15 PREDICTIVE CORE READY ✓',
  ];
  private msgIdx = 0;

  readonly SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT', 'AVAXUSDT', 'ADAUSDT'];

  readonly GROUPS = [
    { key: 'g1PriceAction', label: 'G1 Price Action & Velas', color: '#00f0ff', icon: '📊', weight: '15%' },
    { key: 'g2SmcIct', label: 'G2 SMC/ICT Institucional', color: '#ff00aa', icon: '🏛️', weight: '20%' },
    { key: 'g3Wyckoff', label: 'G3 Wyckoff Intraday', color: '#00ff88', icon: '🌊', weight: '15%' },
    { key: 'g4Fractals', label: 'G4 Fractales & Estructura', color: '#aa00ff', icon: '🔺', weight: '15%' },
    { key: 'g5Volume', label: 'G5 Volume Profile & Flow', color: '#ff8800', icon: '📈', weight: '20%' },
    { key: 'g6Ml', label: 'G6 ML XGBoost', color: '#ffff00', icon: '🤖', weight: '15%' },
  ];

  // ── Computed ───────────────────────────────────────────────────────────
  confidenceColor = computed(() => {
    const c = this.data()?.aiConfidence ?? 0;
    if (c >= 75) return '#00ff88';
    if (c >= 55) return '#ffdd00';
    return '#ff4466';
  });

  directionClass = computed(() => {
    const d = this.data()?.direction;
    if (d === 'BULLISH') return 'bullish';
    if (d === 'BEARISH') return 'bearish';
    return 'neutral';
  });

  groupScores = computed(() => {
    const gs = this.data()?.groupScores;
    if (!gs) return [];
    return this.GROUPS.map(g => ({
      ...g,
      score: (gs as any)[g.key] as number ?? 0,
    }));
  });

  detectivityEntries = computed(() => {
    const d = this.data()?.detectivity;
    if (!d) return [];
    return Object.entries(d).map(([key, value]) => ({ key, value }));
  });

  leftGroups = computed(() => this.groupScores().slice(0, 3));
  rightGroups = computed(() => this.groupScores().slice(3, 6));

  ngOnInit() {
    this.startTerminal();
    this.loadLatest();

    // SignalR live updates
    this.sub = this.signalR.nexus15$.subscribe(payload => {
      if (!payload) return;
      if (payload.symbol?.toUpperCase() === this.selectedSymbol().toUpperCase()) {
        this.data.set(payload);
        this.scanCount.update(n => n + 1);
        this.pushTerminal(`↳ ${payload.symbol} | CONF:${payload.aiConfidence?.toFixed(1)}% | ${payload.direction}`);
      }
    });
  }

  ngOnDestroy() {
    this.sub?.unsubscribe();
    if (this.terminalInterval) clearInterval(this.terminalInterval);
  }

  onSymbolChange(sym: string) {
    this.selectedSymbol.set(sym);
    this.loadLatest();
  }

  runOnDemand() {
    this.isLoading.set(true);
    this.errorMsg.set(null);
    this.pushTerminal(`> MANUAL SCAN: ${this.selectedSymbol()}`);
    this.nexus15Service.analyzeOnDemand(this.selectedSymbol()).subscribe({
      next: r => {
        this.data.set(r);
        this.isLoading.set(false);
        this.scanCount.update(n => n + 1);
        this.pushTerminal(`✓ OK | CONFIDENCE: ${r.aiConfidence?.toFixed(1)}% | DIR: ${r.direction}`);
      },
      error: err => {
        this.isLoading.set(false);
        this.errorMsg.set('Analysis failed. Python Service may be offline.');
        this.pushTerminal(`✗ ERROR: ${err?.message || 'Unknown'}`);
      }
    });
  }

  private loadLatest() {
    this.isLoading.set(true);
    this.nexus15Service.getLatest(this.selectedSymbol()).subscribe({
      next: r => {
        if (r) this.data.set(r);
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false)
    });
  }

  private startTerminal() {
    this.terminalLines.set([]);
    this.terminalInterval = setInterval(() => {
      this.pushTerminal(this.terminalMessages[this.msgIdx % this.terminalMessages.length]);
      this.msgIdx++;
    }, 1800);
  }

  private pushTerminal(line: string) {
    const ts = new Date().toISOString().slice(11, 19);
    const full = `[${ts}] ${line}`;
    this.terminalLines.update(lines => [...lines.slice(-18), full]);
  }

  getGroupDetectivity(groupKey: string): string {
    const d = this.data()?.detectivity;
    if (!d) return '';
    return d[groupKey] || d[`g${groupKey}`] || '';
  }
}
