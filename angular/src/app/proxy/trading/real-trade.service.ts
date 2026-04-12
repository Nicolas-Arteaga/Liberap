import type { TradeConfirmationDto, TradePreviewDto, TradeRequestDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class RealTradeService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  confirm = (input: TradeConfirmationDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, boolean>({
      method: 'POST',
      url: '/api/app/real-trade/confirm',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  getPreview = (input: TradeRequestDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TradePreviewDto>({
      method: 'GET',
      url: '/api/app/real-trade/preview',
      params: { symbol: input.symbol, side: input.side, quantity: input.quantity, leverage: input.leverage },
    },
    { apiName: this.apiName,...config });
}