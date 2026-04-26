import type { ScarAccuracyDto, ScarPredictionDto, ScarResultDto, ScarTemplateAdjustmentDto, ScarTopSetupDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class ScarService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  getAccuracy = (symbol?: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, ScarAccuracyDto>({
      method: 'GET',
      url: '/api/app/scar/accuracy',
      params: { symbol },
    },
    { apiName: this.apiName,...config });
  

  getActiveAlerts = (threshold: number = 3, config?: Partial<Rest.Config>) =>
    this.restService.request<any, ScarResultDto[]>({
      method: 'GET',
      url: '/api/app/scar/active-alerts',
      params: { threshold },
    },
    { apiName: this.apiName,...config });
  

  getAdjustments = (limit: number = 20, config?: Partial<Rest.Config>) =>
    this.restService.request<any, ScarTemplateAdjustmentDto[]>({
      method: 'GET',
      url: '/api/app/scar/adjustments',
      params: { limit },
    },
    { apiName: this.apiName,...config });
  

  getPredictions = (status?: string, limit: number = 50, config?: Partial<Rest.Config>) =>
    this.restService.request<any, ScarPredictionDto[]>({
      method: 'GET',
      url: '/api/app/scar/predictions',
      params: { status, limit },
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
  

  submitFeedback = (predictionId: number, result: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: `/api/app/scar/submit-feedback/${predictionId}`,
      params: { result },
    },
    { apiName: this.apiName,...config });
}