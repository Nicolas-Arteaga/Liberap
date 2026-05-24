import { Injectable, inject } from '@angular/core';
import * as signalR from '@microsoft/signalr';
import { Subject } from 'rxjs';
import { AuthService } from '../core/auth.service';
import { environment } from '../../environments/environment';

export interface AgentLog {
  message: string;
  color?: string;
  timestamp: string;
}

@Injectable({
  providedIn: 'root'
})
export class AgentSignalrService {
  private authService = inject(AuthService);
  private hubConnection: signalR.HubConnection | undefined;
  private connectionPromise: Promise<void> | null = null;

  private logSubject = new Subject<AgentLog>();
  logs$ = this.logSubject.asObservable();

  private stateSubject = new Subject<string>();
  state$ = this.stateSubject.asObservable();

  async startConnection() {
    // Si ya hay una conexión en progreso (cualquier estado), esperar sin duplicar
    if (this.connectionPromise) {
      await this.connectionPromise;
      return;
    }

    // Si ya estaba conectado, ok
    if (this.hubConnection?.state === signalR.HubConnectionState.Connected) return;

    const apiUrl = environment.apis?.default?.url || 'https://localhost:44396';
    const hubUrl = `${apiUrl}/signalr-hubs/agent`;

    // Marcar promesa ANTES de crear el builder para tapar cualquier race condition
    this.connectionPromise = this._buildAndStart(hubUrl);
    try {
      await this.connectionPromise;
    } finally {
      this.connectionPromise = null;
    }
  }

  private async _buildAndStart(hubUrl: string): Promise<void> {
    const connection = new signalR.HubConnectionBuilder()
      .withUrl(hubUrl, {
        accessTokenFactory: () => this.authService.getToken() || ''
      })
      .withAutomaticReconnect([0, 2000, 5000, 10000, 30000])
      .configureLogging(signalR.LogLevel.Information)
      .build();

    connection.on('ReceiveAgentLog', (message: string, color?: string) => {
      this.logSubject.next({
        message,
        color,
        timestamp: new Date().toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      });
    });

    connection.on('ServerStateChanged', (state: string) => {
      this.stateSubject.next(state);
    });

    this.hubConnection = connection;
    await connection.start();
  }

  async stopConnection() {
    if (this.hubConnection) {
      await this.hubConnection.stop();
      this.hubConnection = undefined;
    }
  }
}
