import type { GetMarketCandlesInput, GetMarketDataInput, MarketCandleDto, MarketOrderBookDto, RecentTradeDto, SymbolTickerDto } from './models';
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
  

  getOrderBook = (input: GetMarketDataInput, config?: Partial<Rest.Config>) =>
    this.restService.request<any, MarketOrderBookDto>({
      method: 'GET',
      url: '/api/app/market-data/order-book',
      params: { symbol: input.symbol, limit: input.limit },
    },
    { apiName: this.apiName,...config });
  

  getRecentTrades = (input: GetMarketDataInput, config?: Partial<Rest.Config>) =>
    this.restService.request<any, RecentTradeDto[]>({
      method: 'GET',
      url: '/api/app/market-data/recent-trades',
      params: { symbol: input.symbol, limit: input.limit },
    },
    { apiName: this.apiName,...config });
  

  getTickers = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, SymbolTickerDto[]>({
      method: 'GET',
      url: '/api/app/market-data/tickers',
    },
    { apiName: this.apiName,...config });
}