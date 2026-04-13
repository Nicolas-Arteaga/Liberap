import type { Nexus15ResultDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class Nexus15Service {
  private restService = inject(RestService);
  apiName = 'Default';
  

  analyzeOnDemand = (symbol: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, Nexus15ResultDto>({
      method: 'POST',
      url: '/api/app/nexus15/analyze-on-demand',
      params: { symbol },
    },
    { apiName: this.apiName,...config });
  

  getLatest = (symbol: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, Nexus15ResultDto>({
      method: 'GET',
      url: '/api/app/nexus15/latest',
      params: { symbol },
    },
    { apiName: this.apiName,...config });
}