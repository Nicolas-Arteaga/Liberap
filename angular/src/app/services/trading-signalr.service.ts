import { Injectable, inject } from '@angular/core';
import { Subject } from 'rxjs';
import { TradingSessionDto } from '../proxy/trading/models';
import * as signalR from '@microsoft/signalr';
import { OAuthService } from 'angular-oauth2-oidc';
import { RestService } from '@abp/ng.core';
import { environment } from '../../environments/environment'; // 👈 MEJOR USAR ENVIRONMENT

@Injectable({
    providedIn: 'root'
})
export class TradingSignalrService {
    private oAuthService = inject(OAuthService);

    private sessionStartedSource = new Subject<TradingSessionDto>();
    private sessionEndedSource = new Subject<string>();
    private stageAdvancedSource = new Subject<TradingSessionDto>();

    sessionStarted$ = this.sessionStartedSource.asObservable();
    sessionEnded$ = this.sessionEndedSource.asObservable();
    stageAdvanced$ = this.stageAdvancedSource.asObservable();

    private connection: signalR.HubConnection | null = null;

    constructor() {
        this.startConnection();
    }

    private startConnection() {
        const apiUrl = environment.apiUrl || 'https://localhost:44396';
        const hubUrl = `${apiUrl}/signalr-hubs/trading`;

        this.initConnection(hubUrl);
    }

    private initConnection(hubUrl: string) {
        this.connection = new signalR.HubConnectionBuilder()
            .withUrl(hubUrl, {
                accessTokenFactory: () => this.oAuthService.getAccessToken()
            })
            .withAutomaticReconnect()
            .build();

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

        this.connection.start()
            .then(() => console.log('[SignalR] Conectado al Hub de Trading'))
            .catch(err => console.error('[SignalR] Error de conexión:', err));
    }
}