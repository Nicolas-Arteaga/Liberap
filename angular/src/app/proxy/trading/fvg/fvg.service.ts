import type { FvgAnalyzeResponseDto, FvgScanResponseDto, FvgCascadeResultDto, FvgCascadeScanResponseDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class FvgService {
  private restService = inject(RestService);
  apiName = 'Default';


  analyzeOnDemand = (symbol: string, interval: string = '15m', config?: Partial<Rest.Config>) =>
    this.restService.request<any, FvgAnalyzeResponseDto>({
      method: 'POST',
      url: '/api/app/fvg/analyze-on-demand',
      params: { symbol, interval },
    },
    { apiName: this.apiName, ...config });


  scan = (symbols: string[], interval: string = '15m', config?: Partial<Rest.Config>) =>
    this.restService.request<any, FvgScanResponseDto>({
      method: 'POST',
      url: '/api/app/fvg/scan',
      params: { interval },
      body: symbols,
    },
    { apiName: this.apiName, ...config });


  cascade = (symbol: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, FvgCascadeResultDto>({
      method: 'POST',
      url: '/api/app/fvg/cascade',
      params: { symbol },
    },
    { apiName: this.apiName, ...config });


  cascadeScan = (symbols: string[], config?: Partial<Rest.Config>) =>
    this.restService.request<any, FvgCascadeScanResponseDto>({
      method: 'POST',
      url: '/api/app/fvg/cascade-scan',
      body: symbols,
    },
    { apiName: this.apiName, ...config });
}
