import { Component, AfterViewInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { IonIcon } from "@ionic/angular/standalone";
import { IconService } from 'src/shared/services/icon.service';
import { AuthService } from '../core/auth.service';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [
    CommonModule,
    CardIconComponent,
    GlassButtonComponent,
    CardContentComponent,
    IonIcon
  ],
  templateUrl: './profile.component.html',
  styleUrls: ['./profile.component.scss']
})
export class ProfileComponent implements AfterViewInit {

  private router = inject(Router);
  private iconService = inject(IconService);
  private authService = inject(AuthService);

  isAdmin$ = this.authService.isAdmin$;

  // Datos del trader (mock inicial)
  traderProfile = {
    name: 'Nicolás Arteaga',
    email: 'trader@criptopredictor.com',
    tradingLevel: 'Intermedio',
    joinDate: 'Enero 2026',
    totalProfit: 3250, // USDT
    accuracy: 78, // %
    activeStrategies: 2,
    riskTolerance: 'Moderado' as 'Bajo' | 'Moderado' | 'Alto'
  };

  // API Keys conectadas
  connectedApis = [
    { name: 'Binance', connected: true, lastSync: 'Hace 5 min' },
    { name: 'Coinbase', connected: false },
    { name: 'Kraken', connected: false }
  ];

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  onEditProfile() {
    console.log('Editar perfil de trader');
    // Navegar a edición de perfil
  }

  onConnectExchange() {
    console.log('Conectar Exchange');
    // Lógica para conectar APIs de exchanges
  }

  onApiKeys() {
    console.log('Gestionar API Keys');
    // Mostrar/editar API Keys
  }

  onTradingSettings() {
    console.log('Configuración de Trading');
    // Configurar parámetros de trading
  }

  onAlertsSettings() {
    console.log('Configurar Alertas');
    // Configurar sistema de alertas 1-2-3-4
  }

  onSecurity() {
    console.log('Seguridad API y 2FA');
    // Configurar seguridad
  }

  onBackupData() {
    console.log('Backup de datos');
    // Exportar historial de trades
  }

  onHelp() {
    console.log('Ayuda y Soporte');
    // Abrir documentación/soporte
  }

  onManageUsers() {
    this.router.navigate(['/admin/users/create']);
  }

  onLogout() {
    if (confirm('¿Estás seguro que deseas cerrar sesión?')) {
      console.log('Sesión cerrada - Trader');
      window.location.href = '/login';
    }
  }

  // Métodos auxiliares
  getRiskColor(risk: 'Bajo' | 'Moderado' | 'Alto'): string {
    switch (risk) {
      case 'Bajo': return 'text-success';
      case 'Moderado': return 'text-warning';
      case 'Alto': return 'text-danger';
      default: return 'text-white-50';
    }
  }

  formatCurrency(value: number): string {
    return `$${value.toLocaleString('es-AR')}`;
  }
}




// 🎯 Cambios Realizados Según el Roadmap:
// 1. Información Específica de Trader:
// Stats del trader: Precisión, Ganancia total, Estrategias activas

// Nivel de trader: Intermedio/Avanzado

// Perfil de riesgo: Bajo/Moderado/Alto (con colores)

// 2. Exchanges Conectados:
// Lista de exchanges (Binance, Coinbase, Kraken)

// Estado de conexión (Conectado/Desconectado)

// Última sincronización

// 3. Configuración de Trading:
// API Keys y Seguridad: En lugar de "Métodos de pago"

// Configuración de Trading: Parámetros, apalancamiento, stop-loss

// Sistema de Alertas: Configurar el sistema 1-2-3-4 del roadmap

// Backup y Exportación: Exportar historial de trades

// Ayuda y Soporte: Tutoriales y FAQ específicos de trading

// 4. Visual de Trader:
// Avatar con ícono de cohete 🚀 (en lugar de persona)

// Paleta de colores para riesgo (verde/amarillo/rojo)

// Mensaje final "Trade Responsably"

// 5. Mantengo:
// ✅ Misma estructura de componentes

// ✅ Mismo diseño de cards

// ✅ Mismo sistema de navegación

// ✅ Mismo estilo visual