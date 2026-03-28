import type { FractalStatusDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class FractalAnalysisService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  getStatus = (symbol: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, FractalStatusDto>({
      method: 'GET',
      url: '/api/app/fractal-analysis/status',
      params: { symbol },
    },
    { apiName: this.apiName,...config });
}