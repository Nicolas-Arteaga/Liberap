import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class AgentService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  broadcastSignal = (signal: object, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/agent/broadcast-signal',
      body: signal,
    },
    { apiName: this.apiName,...config });
  

  broadcastSignals = (signals: object[], config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/agent/broadcast-signals',
      body: signals,
    },
    { apiName: this.apiName,...config });
  

  getAuditSummary = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, object>({
      method: 'GET',
      url: '/api/app/agent/audit-summary',
    },
    { apiName: this.apiName,...config });
  

  getOpenPositions = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, object>({
      method: 'GET',
      url: '/api/app/agent/open-positions',
    },
    { apiName: this.apiName,...config });
  

  getRecentTrades = (limit: number = 10, config?: Partial<Rest.Config>) =>
    this.restService.request<any, object>({
      method: 'GET',
      url: '/api/app/agent/recent-trades',
      params: { limit },
    },
    { apiName: this.apiName,...config });
  

  getStrategyStats = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, object>({
      method: 'GET',
      url: '/api/app/agent/strategy-stats',
    },
    { apiName: this.apiName,...config });
  

  getSystemState = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, object>({
      method: 'GET',
      url: '/api/app/agent/system-state',
    },
    { apiName: this.apiName,...config });
  

  getTopSymbols = (limit: number = 5, config?: Partial<Rest.Config>) =>
    this.restService.request<any, object>({
      method: 'GET',
      url: '/api/app/agent/top-symbols',
      params: { limit },
    },
    { apiName: this.apiName,...config });
  

  startAgent = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/agent/start-agent',
    },
    { apiName: this.apiName,...config });
  

  startServer = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/agent/start-server',
    },
    { apiName: this.apiName,...config });
  

  stopAgent = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/agent/stop-agent',
    },
    { apiName: this.apiName,...config });
  

  stopServer = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/agent/stop-server',
    },
    { apiName: this.apiName,...config });
}