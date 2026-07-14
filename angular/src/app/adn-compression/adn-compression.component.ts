import { Component, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';

import { AdnCompressionService } from '../proxy/trading/adn-compression/adn-compression.service';
import { AdnCompressionItemDto } from '../proxy/trading/adn-compression/models';
import { VolatileSymbolsService } from '../shared/services/volatile-symbols.service';

type ViewMode = '5m' | '1d';

const PHASE_LABEL: Record<string, string> = {
  PULLBACK_TO_MA7: 'RESPIRANDO EN MA7',
  COILED: 'ADN COMPRIMIDO',
  EXTENDED: 'EXTENDIDO (EN LAS NUBES)',
  EXHAUSTED: 'AGOTADO — TOCÓ MA25',
};

@Component({
  selector: 'app-adn-compression',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './adn-compression.component.html',
  styleUrls: ['./adn-compression.component.scss'],
})
export class AdnCompressionComponent {
  private adnSvc = inject(AdnCompressionService);
  private volatileSvc = inject(VolatileSymbolsService);

  mode = signal<ViewMode>('5m');
  isLoading = signal(false);
  errorMsg = signal<string | null>(null);
  results = signal<AdnCompressionItemDto[]>([]);
  scannedCount = signal<number | null>(null);
  qualifiedCount = signal<number | null>(null);
  lastScanAt = signal<Date | null>(null);

  modeLabel = computed(() => (this.mode() === '5m' ? 'MICRO (5m) — Scalp' : 'MACRO (1D) — Swing'));

  setMode(m: ViewMode): void {
    if (this.mode() === m) return;
    this.mode.set(m);
    this.results.set([]);
    this.errorMsg.set(null);
  }

  runScan(): void {
    this.isLoading.set(true);
    this.errorMsg.set(null);
    this.volatileSvc.getMostVolatile(100).then(symbols => {
      this.adnSvc.scan(symbols, this.mode()).subscribe({
        next: (res) => {
          this.results.set(res.top10 ?? []);
          this.scannedCount.set(res.scannedCount ?? null);
          this.qualifiedCount.set(res.qualifiedCount ?? null);
          this.lastScanAt.set(new Date());
          this.isLoading.set(false);
        },
        error: (err) => {
          console.error('[ADN-COMPRESSION] scan error:', err);
          this.errorMsg.set('No se pudo escanear el exchange.');
          this.isLoading.set(false);
        },
      });
    });
  }

  phaseLabel(phase?: string): string {
    return PHASE_LABEL[phase ?? ''] ?? phase ?? '—';
  }

  cleanSymbol(sym?: string): string {
    return (sym ?? '').replace('USDT', '');
  }
}
