import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonicModule } from '@ionic/angular';
import { VergeAlert } from './alerts.types';

@Component({
    selector: 'app-alerts',
    standalone: true,
    imports: [CommonModule, IonicModule],
    templateUrl: './alerts.component.html',
    styleUrls: ['./alerts.component.scss']
})
export class AlertsComponent {
    @Input() alerts: VergeAlert[] = [];
    @Input() showOnlyUnread: boolean = false;
    @Input() mode: 'list' | 'overlay' = 'list';

    @Output() alertClick = new EventEmitter<string>();
    @Output() markAsRead = new EventEmitter<string>();

    get filteredAlerts(): VergeAlert[] {
        return this.showOnlyUnread
            ? this.alerts.filter(a => !a.read)
            : this.alerts;
    }

    get activeOverlayAlert(): VergeAlert | undefined {
        // Mostramos la alerta más reciente que sea de Etapa activa (1-4) o Custom y no esté leída
        return this.alerts.find(a =>
            (a.type.startsWith('Stage') || a.type === 'Custom') && !a.read
        );
    }

    onAlertClick(alertId: string) {
        this.alertClick.emit(alertId);
    }

    onMarkAsReadClick(event: Event, alertId: string) {
        event.stopPropagation();
        this.markAsRead.emit(alertId);
    }

    getOverlayTitle(type: string): string {
        switch (type) {
            case 'Stage1':
            case 'Stage2':
                return '¡PREPÁRATE!';
            case 'Stage3':
                return '¡COMPRA AQUÍ!';
            case 'Stage4':
                return '¡SESIÓN FINALIZADA!';
            default:
                return '¡AVISO!';
        }
    }
}
