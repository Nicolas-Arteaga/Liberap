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

            // Normalizar el objeto antes de procesarlo
            const normalized = this.normalizeAlert(alert);

            // Siempre agregamos al servicio para que aparezca en la lista/campanita
            this.alertService.addAlert(normalized);

            // Evitar spam de Toasts: solo lo mostramos si el estado ha cambiado para este par
            const symbol = normalized.crypto || 'Global';
            if (this.lastNotifiedState[symbol] !== normalized.type) {
                console.log(`[SignalR] ✨ Cambio de estado detectado para ${symbol}: ${this.lastNotifiedState[symbol]} -> ${normalized.type}. Disparando Toast.`);
                this.lastNotifiedState[symbol] = normalized.type;
                this.showToastForAlert(normalized);
            } else {
                console.log(`[SignalR] ⏩ Omitiendo Toast para ${symbol} (mismo estado: ${normalized.type})`);
            }
        });

        this.connection.start()
            .then(() => console.warn('[SignalR] 🟢🔥 CONECTADO EXITOSAMENTE AL HUB DE TRADING'))
            .catch(err => console.error('[SignalR] 🔴 Error de conexión:', err));
    }

    private normalizeAlert(alert: any): VergeAlert {
        console.log('[SignalR] 🛠️ Normalizando alerta RAW:', alert);

        // Mapear campos que pueden venir en PascalCase o camelCase desde C# SignalR
        const normalized: any = { ...alert };

        normalized.timestamp = alert.timestamp ? new Date(alert.timestamp) : new Date();

        // Mapeo exhaustivo de campos institucionales
        normalized.crypto = alert.crypto || alert.Crypto || alert.symbol || alert.Symbol || 'AUTO';
        normalized.price = alert.price || alert.Price || alert.entryPrice || alert.EntryPrice || 0;

        // Direction handling (0=Long, 1=Short, etc)
        normalized.direction = alert.direction !== undefined ? alert.direction : alert.Direction;

        normalized.score = alert.score !== undefined ? alert.score : alert.Score;

        // Confidence/WinProb mapping
        const rawConfidence = alert.confidence !== undefined ? alert.confidence : alert.Confidence;
        normalized.confidence = rawConfidence !== undefined ? rawConfidence : (normalized.score || 0);

        normalized.stage = alert.stage !== undefined ? alert.stage : alert.Stage;
        normalized.type = alert.type || alert.Type || 'System';
        normalized.severity = alert.severity || alert.Severity || 'info';

        // Tactical 1% + Fallbacks
        normalized.entryPrice = alert.entryPrice || alert.EntryPrice || alert.price || alert.Price || 0;
        normalized.entryMin = alert.entryMin || alert.EntryMin;
        normalized.entryMax = alert.entryMax || alert.EntryMax;
        normalized.stopLoss = alert.stopLoss || alert.StopLoss || alert.stopLossPrice || alert.StopLossPrice || 0;
        normalized.takeProfit = alert.takeProfit || alert.TakeProfit || alert.takeProfitPrice || alert.TakeProfitPrice || 0;
        normalized.riskRewardRatio = alert.riskRewardRatio || alert.RiskRewardRatio || alert.rrRatio || 0;
        normalized.winProbability = alert.winProbability || alert.WinProbability || alert.winProb || 0;
        normalized.patternName = alert.patternName || alert.PatternName || alert.patternSignal || alert.PatternSignal || 'Institutional Analysis';

        // Whale/Squeeze
        normalized.whaleInfluenceScore = alert.whaleInfluenceScore || alert.WhaleInfluenceScore || alert.whaleInfluence || 0;
        normalized.isSqueeze = alert.isSqueeze || alert.IsSqueeze || false;

        console.log('[SignalR] ✅ Alerta NORMALIZADA:', normalized);
        return normalized as VergeAlert;
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