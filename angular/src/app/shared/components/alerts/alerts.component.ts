import { Component, EventEmitter, Input, Output, HostListener, ChangeDetectorRef } from '@angular/core';
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
        const alert = this.alerts.find(a =>
            (a.type.startsWith('Stage') || a.type === 'Custom' || a.type === 'System') && !a.read
        );
        return alert;
    }

    // --- UI State ---
    position = { x: 0, y: 0 };
    expandedAlertIds = new Set<string>(); // 🧠 Track which alerts are expanded for AI reasoning
    private dragging = false;
    private initialMousePos = { x: 0, y: 0 };

    constructor(private cdr: ChangeDetectorRef) { }

    onMouseDown(event: MouseEvent) {
        if ((event.target as HTMLElement).closest('.close-btn') ||
            (event.target as HTMLElement).closest('button')) return;

        this.dragging = true;
        this.initialMousePos = {
            x: event.clientX - this.position.x,
            y: event.clientY - this.position.y
        };
        event.preventDefault();
    }

    @HostListener('document:mousemove', ['$event'])
    onMouseMove(event: MouseEvent) {
        if (!this.dragging) return;
        this.position.x = event.clientX - this.initialMousePos.x;
        this.position.y = event.clientY - this.initialMousePos.y;
        this.cdr.detectChanges();
    }

    @HostListener('document:mouseup')
    onMouseUp() {
        this.dragging = false;
    }

    onAlertClick(alertId: string) {
        this.alertClick.emit(alertId);
    }

    onMarkAsReadClick(event: Event, alertId: string) {
        event.stopPropagation();
        this.markAsRead.emit(alertId);
        this.position = { x: 0, y: 0 };
        this.expandedAlertIds.delete(alertId);
        this.cdr.detectChanges();
    }

    toggleAIInsights(event: Event, alertId: string) {
        event.stopPropagation();
        if (this.expandedAlertIds.has(alertId)) {
            this.expandedAlertIds.delete(alertId);
        } else {
            this.expandedAlertIds.add(alertId);
        }
        this.cdr.detectChanges();
    }

    isAIInsightsExpanded(alertId: string): boolean {
        return this.expandedAlertIds.has(alertId);
    }

    getOverlayTitle(type: string): string {
        switch (type) {
            case 'Stage1': return 'CONTEXTO DE MERCADO';
            case 'Stage2': return 'PREPARACIÓN TÁCTICA';
            case 'Stage3': return 'ENTRADA CONFIRMADA';
            case 'Stage4': return 'OPERACIÓN FINALIZADA';
            case 'System': return 'INTELIGENCIA DE MERCADO';
            default: return 'ALERTA INSTITUCIONAL';
        }
    }

    getSeverityClass(severity: string): string {
        switch (severity) {
            case 'success': return 'text-success';
            case 'warning': return 'text-warning';
            case 'danger': return 'text-danger';
            default: return 'text-primary';
        }
    }

    getRRRating(rr: number | undefined): string {
        if (!rr) return '';
        if (rr >= 3) return 'EXCELENTE';
        if (rr >= 2) return 'BUENO';
        return 'MODERADO';
    }
}
