import type { FreqtradeCreateBotDto, FreqtradeProfitDto, FreqtradeStatusDto, FreqtradeTradeDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class FreqtradeService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  closeTrade = (tradeId: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: `/api/app/freqtrade/close-trade/${tradeId}`,
    },
    { apiName: this.apiName,...config });
  

  deleteBot = (pair: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'DELETE',
      url: '/api/app/freqtrade/bot',
      params: { pair },
    },
    { apiName: this.apiName,...config });
  

  forceEnter = (pair: string, side: string, stakeAmount: number, leverage: number, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/freqtrade/force-enter',
      params: { pair, side, stakeAmount, leverage },
    },
    { apiName: this.apiName,...config });
  

  forceExit = (tradeId: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: `/api/app/freqtrade/force-exit/${tradeId}`,
    },
    { apiName: this.apiName,...config });
  

  getOpenTrades = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, FreqtradeTradeDto[]>({
      method: 'GET',
      url: '/api/app/freqtrade/open-trades',
    },
    { apiName: this.apiName,...config });
  

  getProfit = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, FreqtradeProfitDto>({
      method: 'GET',
      url: '/api/app/freqtrade/profit',
    },
    { apiName: this.apiName,...config });
  

  getStatus = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, FreqtradeStatusDto>({
      method: 'GET',
      url: '/api/app/freqtrade/status',
    },
    { apiName: this.apiName,...config });
  

  getTradeHistory = (pair?: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, FreqtradeTradeDto[]>({
      method: 'GET',
      url: '/api/app/freqtrade/trade-history',
      params: { pair },
    },
    { apiName: this.apiName,...config });
  

  pauseBot = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/freqtrade/pause-bot',
    },
    { apiName: this.apiName,...config });
  

  reloadConfig = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/freqtrade/reload-config',
    },
    { apiName: this.apiName,...config });
  

  resumeBot = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/freqtrade/resume-bot',
    },
    { apiName: this.apiName,...config });
  

  startBot = (input: FreqtradeCreateBotDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/freqtrade/start-bot',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  stopBot = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/freqtrade/stop-bot',
    },
    { apiName: this.apiName,...config });
  

  updateWhitelist = (pair: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'PUT',
      url: '/api/app/freqtrade/whitelist',
      params: { pair },
    },
    { apiName: this.apiName,...config });
}