import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { ButtonComponent } from 'src/shared/components/button/button.component';

// Estado REAL de la deuda (lo que viene del backend)
type DebtStatus = 'vencida' | 'al-dia';

// Condición de vista (se calcula, NO es estado)
type DebtViewCondition = 'vencida' | 'al-dia' | 'proximo';

interface Debt {
  id: number;
  name: string;
  amount: number;
  status: DebtStatus;  // Solo los estados reales
  type: 'credit-card' | 'loan' | 'bank';
  dueDate: string;
}

@Component({
  selector: 'app-debts',
  standalone: true,
  imports: [CommonModule, CardIconComponent, ButtonComponent],
  templateUrl: './debts.component.html'
})
export class DebtsComponent {
  activeFilter: 'all' | DebtStatus | 'proximo' = 'all';
  
  allDebts: Debt[] = [
    { id: 1, name: 'Tarjeta Visa Platinum', amount: 45000, status: 'vencida', type: 'credit-card', dueDate: '28 Nov 2025' },
    { id: 2, name: 'Préstamo Personal Banco Nación', amount: 120000, status: 'al-dia', type: 'loan', dueDate: '15 Dic 2025' },
    { id: 3, name: 'Tarjeta Mastercard Gold', amount: 28500, status: 'al-dia', type: 'credit-card', dueDate: '20 Dic 2025' },
    { id: 4, name: 'Crédito Hipotecario', amount: 350000, status: 'al-dia', type: 'bank', dueDate: '10 Dic 2025' },
  ];

  // Contadores CORRECTOS (solo estados reales)
  get vencidaCount(): number {
    return this.allDebts.filter(d => d.status === 'vencida').length;  // 1
  }

  get alDiaCount(): number {
    return this.allDebts.filter(d => d.status === 'al-dia').length;   // 3
  }

  // Próximo es un cálculo, NO un estado
  get proximoCount(): number {
    return this.getProximos().length;  // Se calcula
  }

  get totalCount(): number {
    return this.allDebts.length;  // 4, NO 7
  }

  // Filtro principal CORREGIDO
  get filteredDebts(): Debt[] {
    if (this.activeFilter === 'all') {
      return this.allDebts;
    }

    if (this.activeFilter === 'proximo') {
      return this.getProximos();  // Solo deudas al-día con fecha cercana
    }

    return this.allDebts.filter(d => d.status === this.activeFilter);
  }

  // Lógica para "próximo vencimiento" (mock realista)
  private getProximos(): Debt[] {
    // En realidad deberías comparar fechas, esto es un mock
    const hoy = new Date();
    const diasLimite = 7; // Próximos 7 días
    
    return this.allDebts.filter(debt => {
      // Solo deudas al-día
      if (debt.status !== 'al-dia') return false;
      
      // Mock: Si contiene "Dic" y no es muy lejano
      // En producción: calcular diferencia de días con dueDate
      return debt.dueDate.includes('Dic');
    });
  }

  // Estado VISUAL (no confundir con estado real)
  getVisualStatus(debt: Debt): 'al-dia' | 'vencida' | 'proximo' {
    if (debt.status === 'vencida') return 'vencida';
    
    // Si el filtro activo es "proximo", mostrar todas como próximo
    if (this.activeFilter === 'proximo' && this.getProximos().includes(debt)) {
      return 'proximo';
    }
    
    return 'al-dia';
  }

  getStatusLabel(debt: Debt): string {
    const visualStatus = this.getVisualStatus(debt);
    
    switch(visualStatus) {
      case 'vencida': return 'Vencida';
      case 'proximo': return 'Próximo venc.';
      case 'al-dia': return 'Al día';
    }
  }

  getIcon(type: Debt['type']): string {
    switch(type) {
      case 'credit-card': return 'card-outline';
      case 'loan': return 'cash-outline';
      case 'bank': return 'business-outline';
      default: return 'card-outline';
    }
  }
}