import { Component, Input, AfterViewInit, ElementRef, ViewChildren, QueryList } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface ChartData {
  month: string;
  amount: number;
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
  
  // Calcular el máximo para escalar
  get maxAmount(): number {
    if (!this.data.length) return 1;
    return Math.max(...this.data.map(d => d.amount));
  }
  
  // Altura en porcentaje
  getBarHeight(amount: number): number {
    return (amount / this.maxAmount) * 100;
  }
  
  formatAmount(amount: number): string {
    const value = amount / 1000;
    return `$${value % 1 === 0 ? value.toFixed(0) : value.toFixed(1)}k`;
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