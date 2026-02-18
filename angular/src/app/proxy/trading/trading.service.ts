import type { AnalysisLogDto, BacktestResultDto, ConnectExchangeDto, CreateUpdateTradingAlertDto, CreateUpdateTradingStrategyDto, ExchangeConnectionDto, ExecuteTradeDto, GetHistoryInput, GetSignalsInput, MarketAnalysisDto, OpportunityDto, RunBacktestDto, StartSessionDto, TradeOrderDto, TraderProfileDto, TradingAlertDto, TradingSessionDto, TradingSignalDto, TradingStrategyDto, UpdateTraderProfileDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import type { PagedResultDto } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class TradingService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  advanceStage = (sessionId: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingSessionDto>({
      method: 'POST',
      url: `/api/app/trading/advance-stage/${sessionId}`,
    },
    { apiName: this.apiName,...config });
  

  connectExchange = (input: ConnectExchangeDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, ExchangeConnectionDto>({
      method: 'POST',
      url: '/api/app/trading/connect-exchange',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  createAlert = (input: CreateUpdateTradingAlertDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingAlertDto>({
      method: 'POST',
      url: '/api/app/trading/alert',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  createStrategy = (input: CreateUpdateTradingStrategyDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingStrategyDto>({
      method: 'POST',
      url: '/api/app/trading/strategy',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  deactivateAlert = (id: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: `/api/app/trading/${id}/deactivate-alert`,
    },
    { apiName: this.apiName,...config });
  

  deleteStrategy = (id: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'DELETE',
      url: `/api/app/trading/${id}/strategy`,
    },
    { apiName: this.apiName,...config });
  

  executeTrade = (input: ExecuteTradeDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradeOrderDto>({
      method: 'POST',
      url: '/api/app/trading/execute-trade',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  finalizeHunt = (sessionId: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingSessionDto>({
      method: 'POST',
      url: `/api/app/trading/finalize-hunt/${sessionId}`,
    },
    { apiName: this.apiName,...config });
  

  getActiveAlerts = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingAlertDto[]>({
      method: 'GET',
      url: '/api/app/trading/active-alerts',
    },
    { apiName: this.apiName,...config });
  

  getAnalysisLogs = (sessionId: string, limit: number = 50, config?: Partial<Rest.Config>) =>
    this.restService.request<any, AnalysisLogDto[]>({
      method: 'GET',
      url: `/api/app/trading/analysis-logs/${sessionId}`,
      params: { limit },
    },
    { apiName: this.apiName,...config });
  

  getConnections = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, ExchangeConnectionDto[]>({
      method: 'GET',
      url: '/api/app/trading/connections',
    },
    { apiName: this.apiName,...config });
  

  getCurrentSession = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingSessionDto>({
      method: 'GET',
      url: '/api/app/trading/current-session',
    },
    { apiName: this.apiName,...config });
  

  getMarketAnalysisDummy = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, MarketAnalysisDto>({
      method: 'GET',
      url: '/api/app/trading/market-analysis-dummy',
    },
    { apiName: this.apiName,...config });
  

  getOpportunityDummy = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, OpportunityDto>({
      method: 'GET',
      url: '/api/app/trading/opportunity-dummy',
    },
    { apiName: this.apiName,...config });
  

  getOrderHistory = (input: GetHistoryInput, config?: Partial<Rest.Config>) =>
    this.restService.request<any, PagedResultDto<TradeOrderDto>>({
      method: 'GET',
      url: '/api/app/trading/order-history',
      params: { symbol: input.symbol, startDate: input.startDate, endDate: input.endDate, sorting: input.sorting, skipCount: input.skipCount, maxResultCount: input.maxResultCount },
    },
    { apiName: this.apiName,...config });
  

  getProfile = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, TraderProfileDto>({
      method: 'GET',
      url: '/api/app/trading/profile',
    },
    { apiName: this.apiName,...config });
  

  getSignals = (input: GetSignalsInput, config?: Partial<Rest.Config>) =>
    this.restService.request<any, PagedResultDto<TradingSignalDto>>({
      method: 'GET',
      url: '/api/app/trading/signals',
      params: { status: input.status, confidence: input.confidence, sorting: input.sorting, skipCount: input.skipCount, maxResultCount: input.maxResultCount },
    },
    { apiName: this.apiName,...config });
  

  getStrategies = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingStrategyDto[]>({
      method: 'GET',
      url: '/api/app/trading/strategies',
    },
    { apiName: this.apiName,...config });
  

  runBacktest = (input: RunBacktestDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, BacktestResultDto>({
      method: 'POST',
      url: '/api/app/trading/run-backtest',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  startSession = (input: StartSessionDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingSessionDto>({
      method: 'POST',
      url: '/api/app/trading/start-session',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  updateProfile = (input: UpdateTraderProfileDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TraderProfileDto>({
      method: 'PUT',
      url: '/api/app/trading/profile',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  updateStrategy = (id: string, input: CreateUpdateTradingStrategyDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradingStrategyDto>({
      method: 'PUT',
      url: `/api/app/trading/${id}/strategy`,
      body: input,
    },
    { apiName: this.apiName,...config });
}