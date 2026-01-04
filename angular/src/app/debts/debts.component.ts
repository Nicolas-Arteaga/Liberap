import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { ButtonComponent } from 'src/shared/components/button/button.component';

type InterestStatus = 'abusiva' | 'elevada' | 'legal';
type BankProduct = 'credit-card' | 'loan' | 'bank';

interface InterestAnalysis {
  id: number;
  name: string;
  interestRate: number;
  potentialSavings: number;
  status: InterestStatus;
  type: BankProduct;
  analyzedDate: string;
}

@Component({
  selector: 'app-debts',
  standalone: true,
  imports: [CommonModule, CardIconComponent, ButtonComponent],
  templateUrl: './debts.component.html'
})
export class DebtsComponent {
  activeFilter: 'todos' | InterestStatus = 'todos';
  
  allAnalyses: InterestAnalysis[] = [
    { 
      id: 1, 
      name: 'Visa Galicia Platinum', 
      interestRate: 218.5, 
      potentialSavings: 387500, 
      status: 'abusiva', 
      type: 'credit-card', 
      analyzedDate: '03/01/2026' 
    },
    { 
      id: 2, 
      name: 'Préstamo Personal Santander', 
      interestRate: 165.3, 
      potentialSavings: 189200, 
      status: 'elevada', 
      type: 'loan', 
      analyzedDate: '02/01/2026' 
    },
    { 
      id: 3, 
      name: 'Mastercard BBVA Gold', 
      interestRate: 95.5, 
      potentialSavings: 0, 
      status: 'legal', 
      type: 'credit-card', 
      analyzedDate: '01/01/2026' 
    },
  ];

  get abusivaCount(): number {
    return this.allAnalyses.filter(a => a.status === 'abusiva').length;
  }

  get elevadaCount(): number {
    return this.allAnalyses.filter(a => a.status === 'elevada').length;
  }

  get legalCount(): number {
    return this.allAnalyses.filter(a => a.status === 'legal').length;
  }

  get filteredAnalyses(): InterestAnalysis[] {
    if (this.activeFilter === 'todos') {
      return this.allAnalyses;
    }
    return this.allAnalyses.filter(a => a.status === this.activeFilter);
  }

  getStatusLabel(status: InterestStatus): string {
    switch(status) {
      case 'abusiva': return 'Abusiva';
      case 'elevada': return 'Elevada';
      case 'legal': return 'Legal';
      default: return '';
    }
  }

  getStatusColor(status: InterestStatus): 'danger' | 'warning' | 'success' {
    switch(status) {
      case 'abusiva': return 'danger';
      case 'elevada': return 'warning';
      case 'legal': return 'success';
      default: return 'success';
    }
  }

  getIcon(type: BankProduct): string {
    switch(type) {
      case 'credit-card': return 'card-outline';
      case 'loan': return 'cash-outline';
      case 'bank': return 'business-outline';
      default: return 'card-outline';
    }
  }

  formatPercent(value: number): string {
    return `${value.toFixed(1)}%`;
  }
}