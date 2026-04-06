import { Component, inject, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FreqtradePollService } from '../../../services/freqtrade-poll.service';
import { FreqtradeService } from '../../../proxy/freqtrade/freqtrade.service';
import { ToasterService } from '@abp/ng.theme.shared';
import { TradingSignalrService } from '../../../services/trading-signalr.service';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-forzar-acciones-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './forzar-acciones-panel.component.html',
  styleUrls: ['./forzar-acciones-panel.component.scss']
})
export class ForzarAccionesPanelComponent implements OnInit, OnDestroy {
  public pollService = inject(FreqtradePollService);
  private freqtradeService = inject(FreqtradeService);
  private toaster = inject(ToasterService);
  private signalR = inject(TradingSignalrService);

  private scoresSub: Subscription | null = null;
  private scoresMap: Record<string, number> = {};

  isForcingTrade = false;

  ngOnInit() {
    // Escuchar scores en tiempo real desde Redis -> SignalR
    this.scoresSub = this.signalR.superScore$.subscribe(data => {
      if (data && data.symbol) {
        // Normalizar símbolo (quitar / y :) para el mapa local
        const sym = data.symbol.replace('/', '').split(':')[0];
        this.scoresMap[sym] = data.score;
      }
    });
  }

  ngOnDestroy() {
    this.scoresSub?.unsubscribe();
  }

  getScoreForPair(pairName: string): number | string {
    if (!pairName) return '--';
    const barePair = pairName.replace('/', '').split(':')[0];
    return this.scoresMap[barePair] ?? '--';
  }

  forceEnter(pair: string, side: string) {
    this.isForcingTrade = true;
    const displayPair = pair.replace('/', '').split(':')[0];
    this.toaster.info(`Enviando Force ${side.toUpperCase()} para ${displayPair} al motor Freqtrade...`);
    
    this.freqtradeService.forceEnter(pair, side, 100, 10).subscribe({
      next: () => {
        this.toaster.success(`Trade ${side.toUpperCase()} inyectado exitosamente.`);
        this.isForcingTrade = false;
        this.pollService.refresh();
      },
      error: (err) => {
        this.toaster.error('Error al forzar orden. Revisa los logs del bot.', 'Operación fallida');
        this.isForcingTrade = false;
      }
    });
  }
}

