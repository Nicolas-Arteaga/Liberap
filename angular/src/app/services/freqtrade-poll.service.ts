import { Injectable, inject, OnDestroy } from '@angular/core';
import { interval, BehaviorSubject, Subscription, of, throwError } from 'rxjs';
import { switchMap, catchError, startWith } from 'rxjs/operators';
import { FreqtradeService } from '../proxy/freqtrade/freqtrade.service';
import { FreqtradeStatusDto, FreqtradeProfitDto, FreqtradeTradeDto } from '../proxy/freqtrade/models';

@Injectable({
  providedIn: 'root'
})
export class FreqtradePollService implements OnDestroy {
  private freqtradeService = inject(FreqtradeService);
  private subs: Subscription = new Subscription();

  // Estados Reactivos
  status$ = new BehaviorSubject<FreqtradeStatusDto | null>(null);
  profit$ = new BehaviorSubject<FreqtradeProfitDto | null>(null);
  openTrades$ = new BehaviorSubject<FreqtradeTradeDto[]>([]);
  
  // Estado de selección para UI (Compartido entre ActiveBotsTable y BotControlPanel)
  selectedTradeId$ = new BehaviorSubject<number | null>(null);
  selectedPair$ = new BehaviorSubject<string>('');

  private isPolling = false;

  selectTrade(id: number) {
    this.selectedTradeId$.next(id);
    
    // Al seleccionar un trade, también sincronizar el par correspondiente en el panel de control
    const trade = this.openTrades$.value.find(t => t.id === id);
    if (trade) {
      this.selectedPair$.next(trade.pair);
    }
  }

  selectPair(pair: string) {
    this.selectedPair$.next(pair);
  }

  clearSelection() {
    this.selectedTradeId$.next(null);
    this.selectedPair$.next('');
  }

  startPolling() {
    if (this.isPolling) return;
    this.isPolling = true;

    console.log('[FreqtradePollService] Starting polling...');

    // Poll Status (5s)
    this.subs.add(
      interval(5000).pipe(
        startWith(0),
        switchMap(() => this.freqtradeService.getStatus().pipe(
          catchError(err => {
            console.error('[FreqtradePollService] Error fetching status:', err);
            return throwError(() => err);
          })
        ))
      ).subscribe({
        next: data => {
          if (data) this.status$.next(data);
        },
        error: () => {} // Managed by catchError
      })
    );

    // Poll Profit (10s - less frequent)
    this.subs.add(
      interval(10000).pipe(
        startWith(0),
        switchMap(() => this.freqtradeService.getProfit().pipe(catchError(() => of(null))))
      ).subscribe(data => {
        if (data) this.profit$.next(data);
      })
    );

    // Poll Open Trades (5s)
    this.subs.add(
      interval(5000).pipe(
        startWith(0),
        switchMap(() => this.freqtradeService.getOpenTrades().pipe(catchError(() => of([]))))
      ).subscribe(data => {
        const trades = data || [];
        this.openTrades$.next(trades);
        
        // Auto-select the first trade if none is selected
        const currentSelected = this.selectedTradeId$.value;
        if (currentSelected === null && trades.length > 0) {
          this.selectedTradeId$.next(trades[0].id);
        } else if (currentSelected !== null && !trades.some(t => t.id === currentSelected)) {
          // If selected trade no longer exists (closed), clear or select first
          this.selectedTradeId$.next(trades.length > 0 ? trades[0].id : null);
        }
      })
    );
  }

  stopPolling() {
    this.isPolling = false;
  }

  public refresh(): void {
    console.log('[FreqtradePollService] Manual refresh trigger...');
    
    this.freqtradeService.getStatus().subscribe({
      next: data => { if (data) this.status$.next(data); },
      error: err => console.error('[FreqtradePollService] Refresh status error:', err)
    });

    this.freqtradeService.getProfit().subscribe({
      next: data => { if (data) this.profit$.next(data); },
      error: () => {}
    });

    this.freqtradeService.getOpenTrades().subscribe({
      next: data => {
        const trades = data || [];
        this.openTrades$.next(trades);
        // Similar auto-select logic
        const currentSelected = this.selectedTradeId$.value;
        if (currentSelected === null && trades.length > 0) {
          this.selectedTradeId$.next(trades[0].id);
        } else if (currentSelected !== null && !trades.some(t => t.id === currentSelected)) {
          this.selectedTradeId$.next(trades.length > 0 ? trades[0].id : null);
        }
      },
      error: () => {}
    });
  }

  ngOnDestroy() {
    this.stopPolling();
  }
}
