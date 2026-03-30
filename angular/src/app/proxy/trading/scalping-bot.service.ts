import type { BotEquityPointDto, BotTradeDto, ScalpingBotConfigDto, ScalpingBotStatusDto } from './bot/models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class ScalpingBotService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  cancelTrade = (botTradeId: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: `/api/app/scalping-bot/cancel-trade/${botTradeId}`,
    },
    { apiName: this.apiName,...config });
  

  getEquityCurve = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, BotEquityPointDto[]>({
      method: 'GET',
      url: '/api/app/scalping-bot/equity-curve',
    },
    { apiName: this.apiName,...config });
  

  getStatus = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, ScalpingBotStatusDto>({
      method: 'GET',
      url: '/api/app/scalping-bot/status',
    },
    { apiName: this.apiName,...config });
  

  getTrades = (limit: number = 50, config?: Partial<Rest.Config>) =>
    this.restService.request<any, BotTradeDto[]>({
      method: 'GET',
      url: '/api/app/scalping-bot/trades',
      params: { limit },
    },
    { apiName: this.apiName,...config });
  

  startBot = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/scalping-bot/start-bot',
    },
    { apiName: this.apiName,...config });
  

  stopBot = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/scalping-bot/stop-bot',
    },
    { apiName: this.apiName,...config });
  

  updateConfig = (input: ScalpingBotConfigDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'PUT',
      url: '/api/app/scalping-bot/config',
      body: input,
    },
    { apiName: this.apiName,...config });
}