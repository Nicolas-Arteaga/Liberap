import { Component, inject, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { ToggleComponent } from 'src/shared/components/toggle/toggle.component';
import { IconService } from 'src/shared/services/icon.service';
import { IonIcon } from '@ionic/angular/standalone';

interface CryptoOption {
  id: string;
  name: string;
  symbol: string;
  selected: boolean;
}

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

@Component({
  selector: 'app-configure-strategy',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    CardContentComponent,
    GlassButtonComponent,
    ToggleComponent,
    IonIcon
  ],
  templateUrl: './configure-strategy.component.html'
})
export class ConfigureStrategyComponent {
  private iconService = inject(IconService);
  private router = inject(Router);

  // Configuración de la estrategia
  config: StrategyConfig = {
    direction: 'auto',
    selectedCryptos: ['BTC', 'ETH', 'SOL'],
    leverage: 3,
    capital: 100,
    riskLevel: 'medium',
    autoStopLoss: true,
    takeProfit: 4,
    notifications: true
  };

  // Opciones de criptomonedas
  cryptoOptions: CryptoOption[] = [
    { id: 'BTC', name: 'Bitcoin', symbol: 'BTC', selected: true },
    { id: 'ETH', name: 'Ethereum', symbol: 'ETH', selected: true },
    { id: 'SOL', name: 'Solana', symbol: 'SOL', selected: true },
    { id: 'BNB', name: 'Binance Coin', symbol: 'BNB', selected: false },
    { id: 'XRP', name: 'Ripple', symbol: 'XRP', selected: false },
    { id: 'ADA', name: 'Cardano', symbol: 'ADA', selected: false },
    { id: 'AVAX', name: 'Avalanche', symbol: 'AVAX', selected: false },
    { id: 'DOT', name: 'Polkadot', symbol: 'DOT', selected: false },
  ];

  // Opciones de apalancamiento
  leverageOptions = [1, 2, 3, 5, 10];

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  // Toggle selección de cripto
  toggleCrypto(cryptoId: string) {
    const crypto = this.cryptoOptions.find(c => c.id === cryptoId);
    if (crypto) {
      crypto.selected = !crypto.selected;
      
      // Actualizar array de seleccionados
      this.config.selectedCryptos = this.cryptoOptions
        .filter(c => c.selected)
        .map(c => c.id);
    }
  }

  // Seleccionar todas/ninguna
  selectAllCryptos(select: boolean) {
    this.cryptoOptions.forEach(crypto => crypto.selected = select);
    this.config.selectedCryptos = select 
      ? this.cryptoOptions.map(c => c.id) 
      : [];
  }

  // Configurar apalancamiento
  setLeverage(value: number) {
    this.config.leverage = value;
  }

  // Iniciar estrategia
  startStrategy() {
    console.log('Iniciando estrategia con configuración:', this.config);
    
    // Validaciones básicas
    if (this.config.selectedCryptos.length === 0) {
      alert('Selecciona al menos una criptomoneda');
      return;
    }

    if (this.config.capital <= 0) {
      alert('Ingresa un capital válido');
      return;
    }

    // Navegar al dashboard con la estrategia activa
    this.router.navigate(['/dashboard']);
  }

  handleCancel() {
    this.router.navigate(['/']);
  }

  // Métodos auxiliares
  getRiskLabel(risk: 'low' | 'medium' | 'high'): string {
    switch(risk) {
      case 'low': return 'Bajo';
      case 'medium': return 'Moderado';
      case 'high': return 'Alto';
      default: return 'Moderado';
    }
  }

  getRiskColor(risk: 'low' | 'medium' | 'high'): string {
    switch(risk) {
      case 'low': return 'success';
      case 'medium': return 'warning';
      case 'high': return 'danger';
      default: return 'warning';
    }
  }

  getDirectionLabel(direction: 'long' | 'short' | 'auto'): string {
    switch(direction) {
      case 'long': return 'Solo AL ALZA';
      case 'short': return 'Solo A LA BAJA';
      case 'auto': return 'Automático (IA decide)';
      default: return 'Automático';
    }
  }
}


// 1. Transformación Completa:
// "Analizar resumen" → "Configurar Estrategia"

// Subir PDF → Parámetros de trading

// 2. Secciones del Formulario:
// Dirección del Trade: LONG/SHORT/Automático (IA decide)

// Criptomonedas: Grid seleccionable (como en el roadmap)

// Apalancamiento: Botones 1x, 2x, 3x, 5x, 10x

// Capital a Operar: Input + slider (como en el roadmap)

// Configuración Avanzada:

// Nivel de riesgo (Bajo/Moderado/Alto)

// Stop-loss automático

// Take-profit (personalizable %)

// Notificaciones push

// 3. Mantengo:
// ✅ Misma estructura HTML

// ✅ Mismo sistema de header con botón back

// ✅ Mismo diseño de cards

// ✅ Mismo uso de componentes (Toggle, GlassButton, etc.)

// 4. Navegación:
// Al hacer clic en "🚀 Iniciar Caza Automática" → Va al Dashboard (que prepararemos después)

// 🔧 Validaciones:
// Capital mínimo: $10 USDT

// Al menos 1 criptomoneda seleccionada

// Apalancamiento válido (1-10x)

// Take-profit entre 1-50%