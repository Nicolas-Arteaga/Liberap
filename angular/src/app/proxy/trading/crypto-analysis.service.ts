import type { EnhancedAnalysisDto, SentimentAnalysisDto } from './dtos/models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class CryptoAnalysisService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  getEnhancedAnalysis = (sessionId: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, EnhancedAnalysisDto>({
      method: 'GET',
      url: `/api/app/crypto-analysis/enhanced-analysis/${sessionId}`,
    },
    { apiName: this.apiName,...config });
  

  getSentimentForSymbol = (symbol: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, SentimentAnalysisDto>({
      method: 'GET',
      url: '/api/app/crypto-analysis/sentiment-for-symbol',
      params: { symbol },
    },
    { apiName: this.apiName,...config });
}