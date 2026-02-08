import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { InputComponent } from 'src/shared/components/input/input.component';
import { LabelComponent } from 'src/shared/components/label/label.component';
import { SelectComponent } from 'src/shared/components/select/select.component';
import { ToggleComponent } from 'src/shared/components/toggle/toggle.component';
import { PaymentChartComponent } from 'src/shared/components/payment-chart/payment-chart.component';
import { IconService } from 'src/shared/services/icon.service';
import { IonIcon } from '@ionic/angular/standalone';

interface StrategyConfig {
    direction: 'long' | 'short' | 'auto';
    selectedCryptos: string[];
    leverage: number;
    capital: number;
    riskLevel: 'low' | 'medium' | 'high';
    autoStopLoss: boolean;
    takeProfit: number;
    notifications: boolean;
}

interface BacktestConfig {
    symbol: string;
    timeframe: string;
    startDate: string;
    endDate: string;
    strategy: StrategyConfig;
}

interface BacktestResult {
    totalTrades: number;
    winningTrades: number;
    losingTrades: number;
    winRate: number;
    totalProfit: number;
    maxDrawdown: number;
    sharpeRatio: number;
    equityCurve: { date: string; value: number }[];
}

@Component({
    selector: 'app-backtesting',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        CardContentComponent,
        GlassButtonComponent,
        InputComponent,
        LabelComponent,
        SelectComponent,
        ToggleComponent,
        PaymentChartComponent,
        IonIcon
    ],
    templateUrl: './backtesting.component.html'
})
export class BacktestingComponent {
    private iconService = inject(IconService);
    private router = inject(Router);

    // Configuración del backtest
    config: BacktestConfig = {
        symbol: 'BTC/USDT',
        timeframe: '1h',
        startDate: '2024-01-01',
        endDate: '2024-02-01',
        strategy: {
            direction: 'auto',
            selectedCryptos: ['BTC'],
            leverage: 3,
            capital: 1000,
            riskLevel: 'medium',
            autoStopLoss: true,
            takeProfit: 4,
            notifications: false
        }
    };

    // Resultados del backtest (Mock)
    results: BacktestResult | null = null;
    isRunning = false;

    // Opciones
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT'];
    timeframes = ['15m', '1h', '4h', '1d'];

    ngAfterViewInit() {
        this.iconService.fixMissingIcons();
    }

    handleBack() {
        this.router.navigate(['/']);
    }

    runBacktest() {
        this.isRunning = true;
        console.log('▶️ Ejecutando Backtest...', this.config);

        // Simular retraso de procesamiento
        setTimeout(() => {
            this.results = {
                totalTrades: 42,
                winningTrades: 28,
                losingTrades: 14,
                winRate: 66.6,
                totalProfit: 1250.45,
                maxDrawdown: 8.5,
                sharpeRatio: 1.8,
                equityCurve: [
                    { date: 'Jan 1', value: 1000 },
                    { date: 'Jan 5', value: 1050 },
                    { date: 'Jan 10', value: 1020 },
                    { date: 'Jan 15', value: 1100 },
                    { date: 'Jan 20', value: 1150 },
                    { date: 'Jan 25', value: 1120 },
                    { date: 'Feb 1', value: 1250 }
                ]
            };
            this.isRunning = false;
            console.log('✅ Backtest completado:', this.results);
        }, 2000);
    }

    getRiskColor(risk: string): 'success' | 'warning' | 'danger' {
        switch (risk) {
            case 'low': return 'success';
            case 'medium': return 'warning';
            case 'high': return 'danger';
            default: return 'warning';
        }
    }
}
