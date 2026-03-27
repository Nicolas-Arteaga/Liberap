import { Component, Input, AfterViewInit, ElementRef, ViewChildren, QueryList } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface ChartData {
  month: string;
  amount: number;
  isGain?: boolean; // New property for coloring
}

@Component({
  selector: 'app-payment-chart',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './payment-chart.component.html',
  styleUrls: ['./payment-chart.component.scss']
})
export class PaymentChartComponent implements AfterViewInit {
  @Input() data: ChartData[] = [];
  
  // Escalamiento basado en el PnL real (pueden ser negativos)
  get minAmount(): number {
    if (!this.data.length) return 0;
    const min = Math.min(0, ...this.data.map(d => d.amount));
    return min < 0 ? min * 1.1 : 0; // Agregamos margen si es negativo
  }

  get maxAmount(): number {
    if (!this.data.length) return 1;
    const max = Math.max(0.01, ...this.data.map(d => d.amount));
    return max * 1.1; // Agregamos margen
  }
  
  // Altura en porcentaje relativa al rango del movimiento
  getBarHeight(amount: number): number {
    const range = this.maxAmount - this.minAmount;
    if (range === 0) return 50;
    const height = ((amount - this.minAmount) / range) * 100;
    return Math.max(5, height); // Mínimo 5% para visibilidad
  }
  
  formatAmount(amount: number): string {
    const sign = amount > 0 ? '+' : '';
    return `${sign}$${amount.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  ngAfterViewInit() {
    setTimeout(() => {
      this.animateBars();
    }, 100);
  }

  private animateBars() {
    // Animación opcional para las barras
    const bars = document.querySelectorAll('.chart-bar-fill');
    bars.forEach((bar, index) => {
      setTimeout(() => {
        (bar as HTMLElement).style.transform = 'scaleY(1)';
      }, index * 100);
    });
  }
}