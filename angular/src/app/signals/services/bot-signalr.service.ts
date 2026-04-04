import { Injectable, signal, inject } from '@angular/core';
import { HubConnection, HubConnectionBuilder, LogLevel, HttpTransportType } from '@microsoft/signalr';
import { PairBotInfo } from '../models/bot.models';
import { environment } from 'src/environments/environment';
import { OAuthService } from 'angular-oauth2-oidc';

@Injectable({
  providedIn: 'root'
})
export class BotSignalRService {
  private hubConnection: HubConnection;
  
  public activePairs = signal<PairBotInfo[]>([]);
  public botLogs = signal<string[]>([]);
  public isConnected = signal<boolean>(false);
  public lastDataReceived = signal<Date | null>(null);
  public botStatus = signal<string>('stopped');

  public isDataLive = signal<boolean>(false);


  private oauthService = inject(OAuthService);

  constructor() {
    const apiBaseUrl = environment.apis.default.url;
    console.log(`[BotSignalR] 🛰️ Initing connection to: ${apiBaseUrl}/signalr-hubs/bot`);
    
    this.hubConnection = new HubConnectionBuilder()
      .withUrl(`${apiBaseUrl}/signalr-hubs/bot`, {
        accessTokenFactory: () => this.oauthService.getAccessToken()
      }) 
      .configureLogging(LogLevel.Information)
      .withAutomaticReconnect()
      .build();

    this.registerEvents();
    this.startConnection();
  }

  private startConnection() {
    this.hubConnection
      .start()
      .then(() => {
        console.log('✅ BotSignalR: Connected');
        this.isConnected.set(true);
      })
      .catch(err => {
        console.error('❌ BotSignalR: Connection failed:', err);
        this.isConnected.set(false);
      });

    this.hubConnection.onreconnecting((error) => {
      console.warn('⚠️ BotSignalR: Reconnecting...', error);
      this.isConnected.set(false);
    });

    this.hubConnection.onreconnected((connectionId) => {
      console.log('✅ BotSignalR: Reconnected');
      this.isConnected.set(true);
    });

    this.hubConnection.onclose(() => {
      this.isConnected.set(false);
    });
  }

  private registerEvents() {
    this.hubConnection.on('ReceiveSuperScore', (jsonPayload: string) => {
      try {
        const payload = JSON.parse(jsonPayload);
        const newPair: PairBotInfo = {
          symbol: payload.symbol || 'Unknown',
          score: payload.score ?? 0,
          prediction: payload.prediction ?? 0,
          bias: payload.bias ?? 'Neutral',
          atr: payload.atr ?? 0,
          recommendedAction: payload.recommendedAction ?? payload.action ?? 'WAIT'
        };

        console.log(`📥 [BotSignalR] Signal for ${newPair.symbol}: ${newPair.score}`);
        this.updateOrAddPair(newPair);
        this.notifyDataActivity();

      } catch (err) {
        console.error('❌ BotHub: Payload error', err);
      }
    });

    this.hubConnection.on('ReceiveBotLog', (logMsg: string) => {
      this.botLogs.update(logs => [...logs, logMsg].slice(-50));
    });

    this.hubConnection.on('BotStatusChanged', (status: string) => {
      console.log(`🤖 [BotSignalR] Bot status changed to: ${status}`);
      this.botStatus.set(status);
    });
  }

  public updatePairs(pairs: PairBotInfo[]) {
    // Solo ordenamos al recibir la lista completa (ej. carga inicial)
    this.activePairs.set(pairs.sort((a, b) => b.score - a.score));
    this.notifyDataActivity();
  }

  public updateOrAddPair(newPair: PairBotInfo) {
    this.activePairs.update(currentPairs => {
      const idx = currentPairs.findIndex(p => p.symbol === newPair.symbol);
      let updated: PairBotInfo[];
      
      if (idx > -1) {
        updated = [...currentPairs];
        // Actualizamos in-place sin resort para mantener el selector quieto
        updated[idx] = { ...updated[idx], ...newPair };
        return updated; 
      } else {
        // Solo si es nuevo lo añadimos al final
        updated = [...currentPairs, newPair];
        return updated;
      }
    });
  }


  private notifyDataActivity() {
    this.lastDataReceived.set(new Date());
    this.isDataLive.set(true);
    
    // Si no recibimos nada en 15 segundos, bajamos el flag de LIVE
    // (A menos que SignalR diga que está conectado)
    setTimeout(() => {
      const now = new Date().getTime();
      const last = this.lastDataReceived()?.getTime() ?? 0;
      if (now - last > 14000 && !this.isConnected()) {
        this.isDataLive.set(false);
      }
    }, 15000);
  }
}
