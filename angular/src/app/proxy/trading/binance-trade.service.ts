import type { BinanceTradeResultDto, CloseBinanceTradeInputDto, OpenBinanceTradeInputDto } from './dtos/models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class BinanceTradeService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  closeBinanceTrade = (input: CloseBinanceTradeInputDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, BinanceTradeResultDto>({
      method: 'POST',
      url: '/api/app/binance-trade/close-binance-trade',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  openBinanceTrade = (input: OpenBinanceTradeInputDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, BinanceTradeResultDto>({
      method: 'POST',
      url: '/api/app/binance-trade/open-binance-trade',
      body: input,
    },
    { apiName: this.apiName,...config });
}