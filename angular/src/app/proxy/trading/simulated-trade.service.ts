import type { OpenTradeInputDto, SimulatedTradeDto, SimulationPerformanceDto, UpdateTpSlInputDto } from './dtos/models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class SimulatedTradeService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  closeTrade = (tradeId: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, SimulatedTradeDto>({
      method: 'POST',
      url: `/api/app/simulated-trade/close-trade/${tradeId}`,
    },
    { apiName: this.apiName,...config });
  

  getActiveTrades = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, SimulatedTradeDto[]>({
      method: 'GET',
      url: '/api/app/simulated-trade/active-trades',
    },
    { apiName: this.apiName,...config });
  

  getPerformanceStats = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, SimulationPerformanceDto>({
      method: 'GET',
      url: '/api/app/simulated-trade/performance-stats',
    },
    { apiName: this.apiName,...config });
  

  getRecentTrades = (limit: number = 20, config?: Partial<Rest.Config>) =>
    this.restService.request<any, SimulatedTradeDto[]>({
      method: 'GET',
      url: '/api/app/simulated-trade/recent-trades',
      params: { limit },
    },
    { apiName: this.apiName,...config });
  

  getTradeHistory = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, SimulatedTradeDto[]>({
      method: 'GET',
      url: '/api/app/simulated-trade/trade-history',
    },
    { apiName: this.apiName,...config });
  

  getVirtualBalance = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, number>({
      method: 'GET',
      url: '/api/app/simulated-trade/virtual-balance',
    },
    { apiName: this.apiName,...config });
  

  openTrade = (input: OpenTradeInputDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, SimulatedTradeDto>({
      method: 'POST',
      url: '/api/app/simulated-trade/open-trade',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  resolveBinancePriceOnly = (rawSymbol: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, number>({
      method: 'POST',
      url: '/api/app/simulated-trade/resolve-binance-price-only',
      params: { rawSymbol },
    },
    { apiName: this.apiName,...config });
  

  updateTpSl = (tradeId: string, input: UpdateTpSlInputDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'PUT',
      url: `/api/app/simulated-trade/tp-sl/${tradeId}`,
      body: input,
    },
    { apiName: this.apiName,...config });
}