import type { ObAnalyzeResponseDto, ObScanResponseDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class OrderBlockService {
  private restService = inject(RestService);
  apiName = 'Default';

  analyzeOnDemand = (symbol: string, interval: string = '15m', config?: Partial<Rest.Config>) =>
    this.restService.request<any, ObAnalyzeResponseDto>({
      method: 'POST',
      url: '/api/app/order-block/analyze-on-demand',
      params: { symbol, interval },
    },
    { apiName: this.apiName, ...config });

  scan = (symbols: string[], interval: string = '15m', onlyValidated: boolean = true, config?: Partial<Rest.Config>) =>
    this.restService.request<any, ObScanResponseDto>({
      method: 'POST',
      url: '/api/app/order-block/scan',
      params: { interval, onlyValidated },
      body: symbols,
    },
    { apiName: this.apiName, ...config });
}
