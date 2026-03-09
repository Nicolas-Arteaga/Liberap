import type { MonteCarloReportDto, StressTestReportDto, WalkForwardReportDto } from './models';
import type { TradingStyle } from './trading-style.enum';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class ValidationService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  runMonteCarloSimulation = (symbol: string, style: TradingStyle, iterations: number = 10000, runInBackground: boolean = true, config?: Partial<Rest.Config>) =>
    this.restService.request<any, MonteCarloReportDto>({
      method: 'POST',
      url: '/api/app/validation/run-monte-carlo-simulation',
      params: { symbol, style, iterations, runInBackground },
    },
    { apiName: this.apiName,...config });
  

  runStressTest = (symbol: string, style: TradingStyle, runInBackground: boolean = true, config?: Partial<Rest.Config>) =>
    this.restService.request<any, StressTestReportDto>({
      method: 'POST',
      url: '/api/app/validation/run-stress-test',
      params: { symbol, style, runInBackground },
    },
    { apiName: this.apiName,...config });
  

  runWalkForwardAnalysis = (symbol: string, style: TradingStyle, runInBackground: boolean = true, config?: Partial<Rest.Config>) =>
    this.restService.request<any, WalkForwardReportDto>({
      method: 'POST',
      url: '/api/app/validation/run-walk-forward-analysis',
      params: { symbol, style, runInBackground },
    },
    { apiName: this.apiName,...config });
}