import type { LiveShadowReportDto, PaperTradingReportDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class ExecutionService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  runLiveShadowAnalysis = (symbol: string, signalsToAnalyze: number = 100, runInBackground: boolean = true, config?: Partial<Rest.Config>) =>
    this.restService.request<any, LiveShadowReportDto>({
      method: 'POST',
      url: '/api/app/execution/run-live-shadow-analysis',
      params: { symbol, signalsToAnalyze, runInBackground },
    },
    { apiName: this.apiName,...config });
  

  runPaperTradingSimulation = (symbol: string, simulatedDays: number = 30, runInBackground: boolean = true, config?: Partial<Rest.Config>) =>
    this.restService.request<any, PaperTradingReportDto>({
      method: 'POST',
      url: '/api/app/execution/run-paper-trading-simulation',
      params: { symbol, simulatedDays, runInBackground },
    },
    { apiName: this.apiName,...config });
}