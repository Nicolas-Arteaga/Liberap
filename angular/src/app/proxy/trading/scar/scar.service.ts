import type { ScarResultDto, ScarTopSetupDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class ScarService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  getActiveAlerts = (threshold: number = 3, config?: Partial<Rest.Config>) =>
    this.restService.request<any, ScarResultDto[]>({
      method: 'GET',
      url: '/api/app/scar/active-alerts',
      params: { threshold },
    },
    { apiName: this.apiName,...config });
  

  getScore = (symbol: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, ScarResultDto>({
      method: 'GET',
      url: '/api/app/scar/score',
      params: { symbol },
    },
    { apiName: this.apiName,...config });
  

  getTopSetups = (limit: number = 10, config?: Partial<Rest.Config>) =>
    this.restService.request<any, ScarTopSetupDto[]>({
      method: 'GET',
      url: '/api/app/scar/top-setups',
      params: { limit },
    },
    { apiName: this.apiName,...config });
  

  scan = (symbols: string[], config?: Partial<Rest.Config>) =>
    this.restService.request<any, ScarResultDto[]>({
      method: 'POST',
      url: '/api/app/scar/scan',
      body: symbols,
    },
    { apiName: this.apiName,...config });
}