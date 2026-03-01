import { Injectable, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { VergeAlert } from '../shared/components/alerts/alerts.types';
import { Router } from '@angular/router';

@Injectable({
    providedIn: 'root'
})
export class AlertService {
    private alerts = signal<VergeAlert[]>([]);
    public readonly alerts$ = toObservable(this.alerts);

    constructor(private router: Router) {
        this.loadFromStorage();
    }

    addAlert(alert: VergeAlert) {
        console.log('[AlertService] Recibiendo alerta para procesar:', alert);

        const current = this.alerts();

        // Evitar duplicados por id
        if (current.some(a => a.id === alert.id)) {
            console.warn('[AlertService] Alerta duplicada detectada, omitiendo:', alert.id);
            return;
        }

        // Agregar al principio (más recientes primero)
        this.alerts.update(curr => [alert, ...curr].slice(0, 50));
        console.log(`[AlertService] Estado actualizado. Total alertas en memoria: ${this.alerts().length}`);
        this.persistToStorage();
    }

    markAsRead(id: string) {
        this.alerts.update(current =>
            current.map(alert => alert.id === id ? { ...alert, read: true } : alert)
        );
        this.persistToStorage();
    }

    markAllAsRead() {
        this.alerts.update(current =>
            current.map(alert => ({ ...alert, read: true }))
        );
        this.persistToStorage();
    }

    getUnreadCount(): number {
        return this.alerts().filter(a => !a.read).length;
    }

    handleAlertClick(id: string) {
        // Marcar como leída y navegar
        this.markAsRead(id);
        this.router.navigate(['/dashboard']);
    }

    private persistToStorage() {
        try {
            const topRecentAlers = this.alerts(); // Ya está truncado a 50
            localStorage.setItem('verge_alerts', JSON.stringify(topRecentAlers));
        } catch (e) {
            console.warn('Could not persist alerts to localStorage', e);
        }
    }

    private loadFromStorage() {
        try {
            const stored = localStorage.getItem('verge_alerts');
            if (stored) {
                const parsed: any[] = JSON.parse(stored);
                // Asegurar que los timestamps sean Date objects
                const alertsWithDates = parsed.map(a => ({
                    ...a,
                    timestamp: new Date(a.timestamp)
                }));
                this.alerts.set(alertsWithDates);
            }
        } catch (e) {
            console.warn('Could not load alerts from localStorage', e);
        }
    }
}
