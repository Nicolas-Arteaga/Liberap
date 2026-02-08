import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { InputComponent } from 'src/shared/components/input/input.component';
import { LabelComponent } from 'src/shared/components/label/label.component';
import { SelectComponent } from 'src/shared/components/select/select.component';
import { IconService } from 'src/shared/services/icon.service';
import { IonIcon } from '@ionic/angular/standalone';

interface TradeDetails {
  symbol: string;           
  direction: 'LONG' | 'SHORT';
  entryPrice: number;
  currentPrice: number;
  leverage: number;
  suggestedAmount: number;
  takeProfit?: number;
  stopLoss?: number;
  confidence: number;       
}

interface ExecuteTradeRequest {
  symbol: string;
  direction: 'buy' | 'sell';
  amount: number;
  leverage: number;
  takeProfit: number;       
  stopLoss: number;         
  orderType: 'market' | 'limit';
}

@Component({
  selector: 'app-execute-trade',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    CardContentComponent,
    CardIconComponent,
    GlassButtonComponent,
    InputComponent,
    LabelComponent,
    SelectComponent,
    IonIcon
  ],
  templateUrl: './execute-trade.component.html'
})
export class ExecuteTradeComponent {
  private iconService = inject(IconService);
  private router = inject(Router);

  // Mock de detalles de la señal
  tradeDetails: TradeDetails = {
    symbol: 'BTC/USDT',
    direction: 'LONG',
    entryPrice: 68500,
    currentPrice: 68550,
    leverage: 5,
    suggestedAmount: 500,
    takeProfit: 5,
    stopLoss: 2,
    confidence: 85
  };

  // Datos del formulario
  request: ExecuteTradeRequest = {
    symbol: 'BTC/USDT',
    direction: 'buy',
    amount: 500,
    leverage: 5,
    takeProfit: 5,
    stopLoss: 2,
    orderType: 'market'
  };

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  handleBack() {
    this.router.navigate(['/signals']);
  }

  executeTrade() {
    console.log('🚀 Ejecutando Trade:', this.request);
    alert('Trade ejecutado con éxito (Simulación)');
    this.router.navigate(['/dashboard']);
  }

  cancelTrade() {
    this.router.navigate(['/signals']);
  }

  getStatusColor(): 'success' | 'warning' | 'danger' {
    if (this.tradeDetails.confidence >= 80) return 'success';
    if (this.tradeDetails.confidence >= 50) return 'warning';
    return 'danger';
  }

  getRiskSummary() {
    const margin = this.request.amount / this.request.leverage;
    const potentialProfit = this.request.amount * (this.request.takeProfit / 100);
    const potentialLoss = this.request.amount * (this.request.stopLoss / 100);
    
    return {
      margin,
      potentialProfit,
      potentialLoss
    };
  }
}
