import { Injectable, inject } from '@angular/core';
import { RestService, Rest } from '@abp/ng.core';
import { Observable } from 'rxjs';

export interface SentimentAnalysisDto {
    sentiment: string;
    confidence: number;
    scores: Record<string, number>;
}

export interface EnhancedAnalysisDto {
    rsi: number;
    sentiment: SentimentAnalysisDto;
    summary: string;
    recommendation: string;
}

@Injectable({
    providedIn: 'root',
})
export class AIAnalysisService {
    private restService = inject(RestService);
    apiName = 'Default';

    getSentimentForSymbol(symbol: string, config?: Partial<Rest.Config>): Observable<SentimentAnalysisDto> {
        return this.restService.request<any, SentimentAnalysisDto>(
            {
                method: 'GET',
                url: `/api/app/crypto-analysis/sentiment-for-symbol`,
                params: { symbol },
            },
            { apiName: this.apiName, ...config }
        );
    }

    getEnhancedAnalysis(sessionId: string, config?: Partial<Rest.Config>): Observable<EnhancedAnalysisDto> {
        return this.restService.request<any, EnhancedAnalysisDto>(
            {
                method: 'GET',
                url: `/api/app/crypto-analysis/enhanced-analysis/${sessionId}`,
            },
            { apiName: this.apiName, ...config }
        );
    }
}
