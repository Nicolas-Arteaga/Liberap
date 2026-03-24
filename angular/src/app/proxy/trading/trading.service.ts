import type { AnalysisLogDto, CreateUpdateTradingStrategyDto, RecommendedStyleDto, SignalStatsDto, StartSessionDto, TradeConfirmationDto, TradePreviewDto, TradeRequestDto, TradingSessionDto, TradingStrategyDto } from './models';
import type { MarketRegimeType } from './market-regime-type.enum';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class TradingService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  confirm = (input: TradeConfirmationDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, boolean>({
      method: 'POST',
      url: '/api/trading/confirm',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  getPreview = (input: TradeRequestDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradePreviewDto>({
      method: 'POST',
      url: '/api/trading/preview',
      body: input,
    },
    { apiName: this.apiName,...config });

  
  getCurrentSession = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingSessionDto>({
      method: 'GET',
      url: '/api/app/trading/current-session',
    },
    { apiName: this.apiName,...config });

  
  startSession = (input: StartSessionDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingSessionDto>({
      method: 'POST',
      url: '/api/app/trading/start-session',
      body: input,
    },
    { apiName: this.apiName,...config });

  
  advanceStage = (sessionId: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingSessionDto>({
      method: 'POST',
      url: `/api/app/trading/advance-stage/${sessionId}`,
    },
    { apiName: this.apiName,...config });

  
  finalizeHunt = (sessionId: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingSessionDto>({
      method: 'POST',
      url: `/api/app/trading/finalize-hunt/${sessionId}`,
    },
    { apiName: this.apiName,...config });

  
  getAnalysisLogs = (sessionId: string, limit: number = 50, config?: Partial<Rest.Config>) =>
    this.restService.request<any, AnalysisLogDto[]>({
      method: 'GET',
      url: `/api/app/trading/analysis-logs/${sessionId}`,
      params: { limit },
    },
    { apiName: this.apiName,...config });

  
  getSignalStats = (symbol?: string, regime?: MarketRegimeType, config?: Partial<Rest.Config>) =>
    this.restService.request<any, SignalStatsDto>({
      method: 'GET',
      url: '/api/app/trading/signal-stats',
      params: { symbol, regime },
    },
    { apiName: this.apiName,...config });

  
  // POST with symbol as query param (as per generate-proxy.json)
  recommendTradingStyle = (symbol: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, RecommendedStyleDto>({
      method: 'POST',
      url: '/api/app/trading/recommend-trading-style',
      params: { symbol },
    },
    { apiName: this.apiName,...config });

  
  createStrategy = (input: CreateUpdateTradingStrategyDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingStrategyDto>({
      method: 'POST',
      url: '/api/app/trading/strategy',
      body: input,
    },
    { apiName: this.apiName,...config });
}
