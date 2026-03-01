import { Injectable, inject } from '@angular/core';
import { Subject, BehaviorSubject } from 'rxjs';
import { TradingSessionDto } from '../proxy/trading/models';
import * as signalR from '@microsoft/signalr';
import { AuthService } from '../core/auth.service';
import { RestService } from '@abp/ng.core';
import { environment } from '../../environments/environment'; // 👈 MEJOR USAR ENVIRONMENT
import { ToasterService } from '@abp/ng.theme.shared';
import { AlertService } from './alert.service';
import { VergeAlert } from '../shared/components/alerts/alerts.types';

@Injectable({
    providedIn: 'root'
})
export class TradingSignalrService {
    private authService = inject(AuthService);
    private toaster = inject(ToasterService);
    private alertService = inject(AlertService);

    // BehaviorSubject cachea el último evento para componentes que montan tarde
    private sessionStartedSource = new BehaviorSubject<TradingSessionDto | null>(null);
    private sessionEndedSource = new Subject<string>();
    private stageAdvancedSource = new Subject<TradingSessionDto>();

    sessionStarted$ = this.sessionStartedSource.asObservable();
    sessionEnded$ = this.sessionEndedSource.asObservable();
    stageAdvanced$ = this.stageAdvancedSource.asObservable();

    private connection: signalR.HubConnection | null = null;
    private lastNotifiedState: Record<string, string> = {};

    // Obtiene el último valor cacheado sincrónicamente
    getLastSession(): TradingSessionDto | null {
        return this.sessionStartedSource.getValue();
    }

    constructor() {
        console.warn('[SignalR] 🛠️ Instanciando TradingSignalrService e iniciando conexión...');
        this.startConnection();
    }

    private startConnection() {
        const apiUrl = environment.apiUrl || 'https://localhost:44396';
        const hubUrl = `${apiUrl}/signalr-hubs/trading`;

        console.warn(`[SignalR] 🔗 URL del Hub configurada: ${hubUrl}`);
        this.initConnection(hubUrl);
    }

    private initConnection(hubUrl: string) {
        // En ABP, la autenticación por defecto (incluso para APIs) es mediante cookies,
        // no enviando el JWT por header. Para SignalR, solo necesitamos withCredentials: true
        this.connection = new signalR.HubConnectionBuilder()
            .withUrl(hubUrl, {
                accessTokenFactory: () => this.authService.getToken() || ''
            })
            .withAutomaticReconnect([0, 2000, 5000, 10000, 30000])
            .configureLogging(signalR.LogLevel.Information)
            .build();

        this.connection.onreconnecting(error => {
            console.warn('[SignalR] ⚠️ Reconectando...', error);
        });

        this.connection.onreconnected(connectionId => {
            console.warn('[SignalR] ✅ Reconectado!', connectionId);
        });

        this.connection.on('SessionStarted', (session: TradingSessionDto) => {
            console.log('[SignalR] 🚀 Sesión Iniciada:', session);
            this.sessionStartedSource.next(session);
        });

        this.connection.on('SessionEnded', (sessionId: string) => {
            console.log('[SignalR] 🏁 Sesión Finalizada:', sessionId);
            this.sessionEndedSource.next(sessionId);
        });

        this.connection.on('StageAdvanced', (session: TradingSessionDto) => {
            console.log('[SignalR] 📈 Etapa Avanzada:', session);
            this.stageAdvancedSource.next(session);
        });

        this.connection.on('ReceiveAlert', (alert: any) => {
            console.log('[SignalR] 🔔 Alerta RECIBIDA en frontend:', alert);

            // Convertir timestamp string a Date si es necesario
            if (typeof alert.timestamp === 'string') {
                alert.timestamp = new Date(alert.timestamp);
            }

            // Siempre agregamos al servicio para que aparezca en la lista/campanita
            this.alertService.addAlert(alert);

            // Evitar spam de Toasts: solo lo mostramos si el estado ha cambiado para este par
            const symbol = alert.crypto || 'Global';
            const stateKey = `${symbol}_${alert.type}`;

            if (this.lastNotifiedState[symbol] !== alert.type) {
                console.log(`[SignalR] ✨ Cambio de estado detectado para ${symbol}: ${this.lastNotifiedState[symbol]} -> ${alert.type}. Disparando Toast.`);
                this.lastNotifiedState[symbol] = alert.type;
                this.showToastForAlert(alert);
            } else {
                console.log(`[SignalR] ⏩ Omitiendo Toast para ${symbol} (mismo estado: ${alert.type})`);
            }
        });

        this.connection.start()
            .then(() => console.warn('[SignalR] 🟢🔥 CONECTADO EXITOSAMENTE AL HUB DE TRADING'))
            .catch(err => console.error('[SignalR] 🔴 Error de conexión:', err));
    }

    private showToastForAlert(alert: VergeAlert) {
        console.log('[SignalR] 🍞 Ejecutando showToastForAlert() para:', alert.title);

        let life = 8000;
        let method: 'info' | 'success' | 'warn' | 'error' = 'info';

        switch (alert.type) {
            case 'Stage1':
                life = 5000;
                method = 'info';
                break;
            case 'Stage2':
                life = 8000;
                method = 'warn';
                break;
            case 'Stage3':
                life = 0; // Permanente
                method = 'success';
                break;
            case 'Stage4':
                life = 10000;
                method = alert.severity === 'danger' ? 'error' : 'success';
                break;
            default:
                life = 8000;
                method = 'info';
                break;
        }

        console.log(`[SignalR] 🍞 Disparando Toast ABP [${method}] con duración ${life}ms`);

        // ABP Toaster options
        const options = { life };

        if (method === 'info') this.toaster.info(alert.message, alert.title, options);
        else if (method === 'success') this.toaster.success(alert.message, alert.title, options);
        else if (method === 'warn') this.toaster.warn(alert.message, alert.title, options);
        else if (method === 'error') this.toaster.error(alert.message, alert.title, options);
    }
}