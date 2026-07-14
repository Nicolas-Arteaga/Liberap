import type { AdnCompressionScanResponseDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class AdnCompressionService {
  private restService = inject(RestService);
  apiName = 'Default';

  scan = (symbols: string[], timeframe: string = '5m', config?: Partial<Rest.Config>) =>
    this.restService.request<any, AdnCompressionScanResponseDto>({
      method: 'POST',
      url: '/api/app/adn-compression/scan',
      params: { timeframe },
      body: symbols,
    },
    { apiName: this.apiName, ...config });
}
