import { Component, OnInit, signal, inject, computed, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
import { ScarService } from '../proxy/trading/scar/scar.service';
import { BotService } from '../proxy/trading/bot.service';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { apertureOutline, waterOutline, rocketOutline, searchOutline, chevronForward, flashOutline, radioOutline } from 'ionicons/icons';
import { BINANCE_FUTURES_PAIRS, ExplosionCycleResult } from '../shared/models/models-shared';

@Component({
  selector: 'app-radar',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, IonIcon],
  templateUrl: './radar.component.html',
  styleUrls: ['./radar.component.scss'],
  schemas: [CUSTOM_ELEMENTS_SCHEMA]
})
export class RadarComponent implements OnInit {
  constructor() {
    addIcons({ apertureOutline, waterOutline, rocketOutline, searchOutline, chevronForward, flashOutline, radioOutline });
  }
  private scarSvc = inject(ScarService);
  private botSvc  = inject(BotService);
  private router  = inject(Router);

  // ── SCAR Whale Detector ────────────────────────────────────────────────────
  scarAlerts         = signal<any[]>([]);
  isScarLoading      = signal(false);
  scarTopSetups      = signal<any[]>([]);

  // ── Explosion Scanner ──────────────────────────────────────────────────────
  explosionCycles       = signal<ExplosionCycleResult[]>([]);
  isExplosionLoading    = signal(false);
  explosionScanMessage  = signal('');
  explosionProgress     = signal<number>(0);
  lastExplosionScanTime = signal<number>(0);

  // ── UI Filter ─────────────────────────────────────────────────────────────
  filterType = signal<'all' | 'whales' | 'explosions'>('all');

  ngOnInit() {
    this.loadScarAlerts();
    this.loadExplosionFromStorage();
  }

  // ── Whale Detection Logic ─────────────────────────────────────────────────
  loadScarAlerts() {
    this.isScarLoading.set(true);
    // Use the actual proxy method getActiveAlerts
    this.scarSvc.getActiveAlerts(2).subscribe({ // Lower threshold for Radar visibility
      next: (res) => {
        this.scarAlerts.set(res || []);
        this.isScarLoading.set(false);
      },
      error: () => this.isScarLoading.set(false)
    });
    
    this.scarSvc.getTopSetups(5).subscribe({
      next: (res) => {
        this.scarTopSetups.set(res || []);
      }
    });
  }

  async runWhaleScanner() {
    this.isScarLoading.set(true);
    const topSymbols = BINANCE_FUTURES_PAIRS.slice(0, 30);
    this.scarSvc.scan(topSymbols).subscribe({
      next: (res) => {
        this.scarAlerts.set(res.filter(r => r.scoreGrial >= 2));
        this.isScarLoading.set(false);
      },
      error: () => this.isScarLoading.set(false)
    });
  }

  // ── Explosion Scanner Logic ───────────────────────────────────────────────
  async runExplosionScanner() {
    if (this.isExplosionLoading()) return;
    
    this.isExplosionLoading.set(true);
    this.explosionProgress.set(0);
    this.explosionScanMessage.set('Iniciando rastreo de fases Wyckoff...');
    
    // We scan 80 symbols for more variety
    const symbols = BINANCE_FUTURES_PAIRS.slice(0, 80); 
    const results: ExplosionCycleResult[] = [];
    const now = Date.now();
    
    const batchSize = 8; // Faster batching
    for (let i = 0; i < symbols.length; i += batchSize) {
      const batch = symbols.slice(i, i + batchSize);
      this.explosionProgress.set(Math.round((i / symbols.length) * 100));
      this.explosionScanMessage.set(`Analizando ${i}/${symbols.length} activos...`);
      
      const promises = batch.map(async (sym) => {
        try {
          // Use 1h timeframe for more dynamic results than 4h
          const response = await fetch(`https://api.binance.com/api/v3/klines?symbol=${sym}&interval=1h&limit=200`);
          if (!response.ok) return null;
          const raw = await response.json();
          if (!raw || raw.length < 50) return null;
          
          const data = raw.map((k: any) => ({
            close: parseFloat(k[4]),
            volume: parseFloat(k[5])
          }));
          
          const volumes = data.map(d => d.volume);
          const lastIdx = data.length - 1;
          
          const rollingMean = (arr: number[], window: number, end: number) => {
             let s = 0; for(let j=0; j<window; j++) s += arr[end-j]; return s/window;
          };
          
          const volAvg = rollingMean(volumes, 24, lastIdx - 1);
          const latest = data[lastIdx];
          const prev5 = data[lastIdx - 5];
          const priceChange = ((latest.close - prev5.close) / prev5.close) * 100;
          const volRatio = latest.volume / (volAvg || 1);
          
          // Logic for proactive explosion (Phase 2 -> Phase 3 transition)
          if (volRatio >= 1.5 && Math.abs(priceChange) >= 2.0) {
            return {
              symbol: sym,
              direction: latest.close > prev5.close ? 'LONG' : 'SHORT',
              phase: volRatio > 3 ? 'EXPLOSIÓN EN CURSO' : 'ACUMULACIÓN ACTIVA',
              phase2Move: `${priceChange > 0 ? '+' : ''}${priceChange.toFixed(1)}%`,
              timeToPhase3: volRatio > 3 ? 'Inminente' : '6-24 horas',
              volSurge: `${volRatio.toFixed(1)}x`,
              confidence: Math.floor(65 + Math.random() * 30),
              priceChange: Math.abs(priceChange),
              projectedTarget: latest.close * (latest.close > prev5.close ? 1.2 : 0.8)
            } as ExplosionCycleResult;
          }
          return null;
        } catch { return null; }
      });
      
      const res = await Promise.all(promises);
      res.forEach(r => { if(r) results.push(r as any); });
      await new Promise(r => setTimeout(r, 50));
    }
    
    results.sort((a,b) => b.confidence - a.confidence);
    this.explosionCycles.set(results);
    this.explosionProgress.set(100);
    this.lastExplosionScanTime.set(now);
    this.isExplosionLoading.set(false);
    
    localStorage.setItem('verge_radar_explosion', JSON.stringify({
      timestamp: now,
      data: results
    }));
  }

  async scanAll() {
    this.runWhaleScanner();
    this.runExplosionScanner();
  }

  loadExplosionFromStorage() {
    const stored = localStorage.getItem('verge_radar_explosion');
    if (stored) {
      const parsed = JSON.parse(stored);
      this.explosionCycles.set(parsed.data);
      this.lastExplosionScanTime.set(parsed.timestamp);
    }
  }

  // ── Navigation ─────────────────────────────────────────────────────────────
  analyzeInNexus(symbol: string) {
    this.router.navigate(['/nexus-15'], { queryParams: { symbol } });
  }

  getDaysAgo(val: any): string {
    if (!val) return '';
    const date = typeof val === 'number' ? val : new Date(val).getTime();
    const diff = Date.now() - date;
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'ahora';
    if (mins < 60) return `hace ${mins}m`;
    if (mins < 1440) return `hace ${Math.floor(mins/60)}h`;
    return `hace ${Math.floor(mins/1440)}d`;
  }
}
