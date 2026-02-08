import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { ToggleComponent } from 'src/shared/components/toggle/toggle.component';
import { IconService } from 'src/shared/services/icon.service';
import { IonIcon } from '@ionic/angular/standalone';

interface Alert {
    id: number;
    type: 'preparation' | 'buy' | 'warning' | 'sell';
    crypto: string;
    price: number;
    message: string;
    timestamp: string;
    active: boolean;
    channels: ('push' | 'email' | 'telegram')[];
}

interface AlertConfig {
    stage1: { enabled: boolean; sound: boolean; channels: string[] };
    stage2: { enabled: boolean; sound: boolean; channels: string[] };
    stage3: { enabled: boolean; sound: boolean; channels: string[] };
    stage4: { enabled: boolean; sound: boolean; channels: string[] };
}

@Component({
    selector: 'app-alerts',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        CardContentComponent,
        CardIconComponent,
        GlassButtonComponent,
        ToggleComponent,
        IonIcon
    ],
    templateUrl: './alerts.component.html'
})
export class AlertsSystemComponent {
    private iconService = inject(IconService);
    private router = inject(Router);

    // Configuración de etapas 1-2-3-4
    config: AlertConfig = {
        stage1: { enabled: true, sound: true, channels: ['push'] },
        stage2: { enabled: true, sound: true, channels: ['push', 'telegram'] },
        stage3: { enabled: false, sound: true, channels: ['push', 'email'] },
        stage4: { enabled: true, sound: true, channels: ['push', 'telegram', 'email'] }
    };

    // Canales globales disponibles
    channels = [
        { id: 'push', name: 'Notificaciones Push', icon: 'notifications-outline', checked: true },
        { id: 'email', name: 'Correo Electrónico', icon: 'mail-outline', checked: false },
        { id: 'telegram', name: 'Telegram Bot', icon: 'paper-plane-outline', checked: true }
    ];

    // Lista de alertas activas
    activeAlerts: Alert[] = [
        {
            id: 1,
            type: 'preparation',
            crypto: 'BTC/USDT',
            price: 68200,
            message: 'Fase 1: Preparación detectada',
            timestamp: 'Hace 5 min',
            active: true,
            channels: ['push']
        },
        {
            id: 2,
            type: 'buy',
            crypto: 'ETH/USDT',
            price: 3650,
            message: 'Fase 2: Confirmación de COMPRA',
            timestamp: 'Hace 12 min',
            active: true,
            channels: ['push', 'telegram']
        },
        {
            id: 3,
            type: 'warning',
            crypto: 'SOL/USDT',
            price: 145,
            message: 'Fase 3: Volatilidad alta',
            timestamp: 'Hace 1 hora',
            active: false,
            channels: ['push']
        }
    ];

    ngAfterViewInit() {
        this.iconService.fixMissingIcons();
    }

    handleBack() {
        this.router.navigate(['/']);
    }

    toggleStage(stage: keyof AlertConfig) {
        this.config[stage].enabled = !this.config[stage].enabled;
        console.log(`Etapa ${stage} ${this.config[stage].enabled ? 'Activada' : 'Desactivada'}`);
    }

    createManualAlert() {
        console.log('Creando alerta manual...');
        alert('Funcionalidad para crear alerta manual abierta');
    }

    toggleAlert(alertId: number) {
        const alertItem = this.activeAlerts.find(a => a.id === alertId);
        if (alertItem) {
            alertItem.active = !alertItem.active;
            console.log(`Alerta ${alertId} ${alertItem.active ? 'Activada' : 'Desactivada'}`);
        }
    }

    getStatusColor(type: string): 'primary' | 'success' | 'warning' | 'danger' {
        switch (type) {
            case 'preparation': return 'primary';
            case 'buy': return 'success';
            case 'warning': return 'warning';
            case 'sell': return 'danger';
            default: return 'primary';
        }
    }

    getIconForType(type: string): string {
        switch (type) {
            case 'preparation': return ' flashlight-outline';
            case 'buy': return 'trending-up-outline';
            case 'warning': return 'alert-circle-outline';
            case 'sell': return 'trending-down-outline';
            default: return 'notifications-outline';
        }
    }
}
