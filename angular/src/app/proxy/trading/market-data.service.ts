import type { GetMarketCandlesInput, MarketCandleDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class MarketDataService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  getCandles = (input: GetMarketCandlesInput, config?: Partial<Rest.Config>) =>
    this.restService.request<any, MarketCandleDto[]>({
      method: 'GET',
      url: '/api/app/market-data/candles',
      params: { symbol: input.symbol, interval: input.interval, limit: input.limit },
    },
    { apiName: this.apiName,...config });
}