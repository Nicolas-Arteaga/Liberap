import { Injectable, inject, OnDestroy } from '@angular/core';
import { interval, BehaviorSubject, Subscription, of, startWith } from 'rxjs';
import { switchMap, catchError, filter } from 'rxjs/operators';
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

  private isPolling = false;

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
        this.openTrades$.next(data || []);
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
      next: data => this.openTrades$.next(data || []),
      error: () => {}
    });
  }

  ngOnDestroy() {
    this.stopPolling();
  }
}

import { throwError } from 'rxjs';
