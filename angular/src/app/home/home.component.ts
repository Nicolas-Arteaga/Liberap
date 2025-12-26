import { Component, AfterViewInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { IconService } from 'src/shared/services/icon.service';
import { RouterLink } from '@angular/router';
import { DisabledDirective } from "../../../node_modules/@abp/ng.theme.shared/index";

interface HomeDebt {
  name: string;
  amount: number;
  icon: string;
  status: 'vencida' | 'al-dia';
}

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [
    CommonModule,
    CardContentComponent,
    CardIconComponent,
    GlassButtonComponent,
    RouterLink
],
  templateUrl: './home.component.html'
})
export class HomeComponent implements AfterViewInit {
  
  private iconService = inject(IconService);  
  
  recentDebts: HomeDebt[] = [
    { name: 'Tarjeta Visa', amount: 45000, icon: 'card-outline', status: 'vencida' },
    { name: 'Préstamo Personal', amount: 120000, icon: 'cash-outline', status: 'al-dia' },
    { name: 'Tarjeta Mastercard', amount: 28500, icon: 'card-outline', status: 'al-dia' },
  ];
  
  ngAfterViewInit() {
    this.iconService.fixMissingIcons();  
  }

  getStatusLabel(status: 'vencida' | 'al-dia'): string {
    return status === 'vencida' ? 'Vencida' : 'Al día';
  }
}