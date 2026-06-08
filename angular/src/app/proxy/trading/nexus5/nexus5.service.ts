import type { Nexus5ResultDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class Nexus5Service {
  private restService = inject(RestService);
  apiName = 'Default';
  

  analyzeAllCandidates = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, Nexus5ResultDto[]>({
      method: 'POST',
      url: '/api/app/nexus5/analyze-all-candidates',
    },
    { apiName: this.apiName,...config });
  

  analyzeOnDemand = (symbol: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, Nexus5ResultDto>({
      method: 'POST',
      url: '/api/app/nexus5/analyze-on-demand',
      params: { symbol },
    },
    { apiName: this.apiName,...config });
  

  analyzeTopAvailable = (topN: number = 5, config?: Partial<Rest.Config>) =>
    this.restService.request<any, Nexus5ResultDto[]>({
      method: 'POST',
      url: '/api/app/nexus5/analyze-top-available',
      params: { topN },
    },
    { apiName: this.apiName,...config });
  

  getLatest = (symbol: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, Nexus5ResultDto>({
      method: 'GET',
      url: '/api/app/nexus5/latest',
      params: { symbol },
    },
    { apiName: this.apiName,...config });
}