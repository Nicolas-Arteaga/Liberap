import { Component, inject, signal, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormControl, FormGroup, Validators } from '@angular/forms';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { chevronDownOutline, informationCircleOutline, syncOutline } from 'ionicons/icons';
import { BotSignalRService } from '../../services/bot-signalr.service';
import { FreqtradeService } from '../../../proxy/freqtrade/freqtrade.service';
import { FreqtradeCreateBotDto } from '../../../proxy/freqtrade/models';
import { ToasterService } from '@abp/ng.theme.shared';

@Component({
  selector: 'app-create-bot-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, IonIcon],
  template: `
    <div class="create-bot-container">
      <h3>Crear Bot (Freqtrade)</h3>

      <div class="form-group" [formGroup]="botForm">
        <label>Tipo:</label>
        <div class="type-selector">
          <label class="radio-label">
            <input type="radio" value="VergeFreqAIStrategy" formControlName="type">
            <span class="custom-radio"></span>
            Scalping (FreqAI)
          </label>
          <label class="radio-label mt-2">
            <input type="radio" value="VergeTestStrategy" formControlName="type">
            <span class="custom-radio"></span>
            Test Strategy (Cruce MA)
          </label>
        </div>
      </div>

      <div class="form-group" [formGroup]="botForm">
        <label>Par:</label>
        <div class="select-wrapper">
          <select formControlName="pair">
            <option *ngIf="!botForm.get('pair')?.value" value="">-- SELECCIONA PAR --</option>
            <option *ngFor="let p of activePairs(); trackBy: trackPair" [value]="p.symbol">
              {{ p.symbol }} (Score: {{ p.score }})
            </option>
          </select>
          <ion-icon name="chevron-down-outline"></ion-icon>
        </div>
      </div>

      <div class="form-group" [formGroup]="botForm">
        <label>Timeframe:</label>
        <div class="select-wrapper">
          <select formControlName="timeframe">
            <option value="1m">1m</option>
            <option value="5m">5m</option>
            <option value="15m">15m</option>
            <option value="1h">1h</option>
          </select>
          <span class="asset-label">Candle</span>
        </div>
      </div>

      <div class="form-group" [formGroup]="botForm">
        <label>Capital:</label>
        <div class="input-wrapper">
          <input type="number" formControlName="stakeAmount">
          <span class="asset-label">USDT</span>
        </div>
      </div>

      <div class="row" [formGroup]="botForm">
        <div class="form-group half">
          <label>Take Profit:</label>
          <div class="input-wrapper simple">
            <input type="number" step="0.1" formControlName="tp">
            <span class="unit">%</span>
          </div>
        </div>
        <div class="form-group half">
          <label>Stop Loss:</label>
          <div class="input-wrapper simple">
            <input type="number" step="0.1" formControlName="sl">
            <span class="unit">%</span>
          </div>
        </div>
      </div>

      <div class="form-group">
        <label>Apalancamiento:</label>
        <div class="leverage-control">
          <span class="value">{{ leverage }}x</span>
          <div class="btns">
            <button class="btn-increment" (click)="updateLeverage(-1)">-</button>
            <button class="btn-increment" (click)="updateLeverage(1)">+</button>
          </div>
        </div>
      </div>

      <button class="btn-start" [disabled]="isLoading" (click)="startBot()">
        {{ isLoading ? 'Iniciando...' : 'Iniciar Bot' }}
      </button>

      <div *ngIf="isLoading" class="mt-2 text-center text-xs text-white-50">
        <ion-icon name="sync-outline" class="animate-spin"></ion-icon>
        Conectando con motor Freqtrade...
      </div>
    </div>
  `,
  styles: [`
    .create-bot-container {
      background: rgba(21, 26, 38, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 16px;
      padding: 24px;
      color: white;
      height: 100%;
    }

    h3 { margin-bottom: 24px; font-size: 18px; font-weight: 700; color: #f0f6fc; }

    .form-group {
      margin-bottom: 20px;
      label { display: block; margin-bottom: 8px; font-size: 13px; color: #8b949e; }
    }

    .type-selector {
      display: flex;
      gap: 16px;
      
      .radio-label {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        cursor: pointer;
        
        input { display: none; }
        .custom-radio {
          width: 16px;
          height: 16px;
          border: 2px solid #57606a;
          border-radius: 50%;
          position: relative;
        }

        input:checked + .custom-radio {
          border-color: #26a69a;
          &::after {
            content: '';
            position: absolute;
            width: 8px;
            height: 8px;
            background: #26a69a;
            border-radius: 50%;
            top: 50%; left: 50%; transform: translate(-50%, -50%);
          }
        }
      }
    }

    .select-wrapper, .input-wrapper {
      position: relative;
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      display: flex;
      align-items: center;
      
      select, input {
        width: 100%;
        background: transparent;
        border: none;
        color: white;
        padding: 10px 12px;
        font-size: 14px;
        outline: none;
        appearance: none;

        option {
          background-color: #161b22;
          color: white;
          padding: 10px;
        }
      }

      ion-icon { position: absolute; right: 12px; color: #8b949e; }
      .asset-label { position: absolute; right: 12px; color: #8b949e; font-size: 12px; }
      .unit { position: absolute; right: 12px; color: #26a69a; font-size: 14px; font-weight: bold; }
    }

    .row { display: flex; gap: 16px; }
    .half { flex: 1; }

    .leverage-control {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 10px 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      
      .value { color: #8b949e; font-weight: bold; }
      .btns { display: flex; gap: 10px; }
      .btn-increment { background: none; border: none; color: #26a69a; font-size: 20px; cursor: pointer; font-weight: bold; }
    }

    .btn-start {
      width: 100%;
      background: #26a69a;
      border: none;
      border-radius: 8px;
      color: white;
      padding: 12px;
      font-weight: 700;
      margin-top: 10px;
      cursor: pointer;
      box-shadow: 0 4px 15px rgba(38, 166, 154, 0.3);
      transition: all 0.2s;
      
      &:hover:not(:disabled) { filter: brightness(1.1); transform: translateY(-1px); }
      &:disabled { opacity: 0.6; cursor: not-allowed; }
    }

    .animate-spin {
      animation: spin 1s linear infinite;
    }
    @keyframes spin { from {transform: rotate(0deg);} to {transform: rotate(360deg);} }
  `]
})
export class CreateBotFormComponent {
  private botSignalRService = inject(BotSignalRService);
  private freqtradeService = inject(FreqtradeService);
  private toaster = inject(ToasterService);

  activePairs = this.botSignalRService.activePairs;
  
  botForm = new FormGroup({
    type: new FormControl('VergeFreqAIStrategy'),
    pair: new FormControl('', Validators.required),
    timeframe: new FormControl('15m'),
    stakeAmount: new FormControl(100),
    tp: new FormControl(2.0),
    sl: new FormControl(1.0)
  });

  leverage = 10;
  isLoading = false;
  private isInitialized = false;

  constructor() {
    addIcons({ chevronDownOutline, informationCircleOutline, syncOutline });
    
    // Inicialización inteligente: solo la primera vez que vienen pares
    effect(() => {
      const pairs = this.activePairs();
      const currentPair = this.botForm.get('pair')?.value;
      if (pairs.length > 0 && !this.isInitialized && !currentPair) {
        console.log(`[CreateBot] 🚀 Inicialización de par por defecto: ${pairs[0].symbol}`);
        this.botForm.patchValue({ pair: pairs[0].symbol });
        this.isInitialized = true;
      }
    }, { allowSignalWrites: true });
  }

  trackPair(index: number, item: any) {
    return item.symbol;
  }

  updateLeverage(delta: number) {
    this.leverage = Math.max(1, this.leverage + delta);
  }

  onPairChange() {
    console.log(`Par seleccionado: ${this.botForm.get('pair')?.value}`);
  }

  startBot() {
    if (this.botForm.invalid) {
      this.toaster.warn('Completa todos los campos obligatorios.');
      return;
    }

    const formVal = this.botForm.value;
    const pair = formVal.pair!;

    if (confirm(`¿Iniciar motor Freqtrade para ${pair}?`)) {
      this.isLoading = true;
      
      const input: FreqtradeCreateBotDto = {
        pair: pair,
        timeframe: formVal.timeframe!,
        stakeAmount: formVal.stakeAmount!,
        tpPercent: formVal.tp!,
        slPercent: formVal.sl!,
        leverage: this.leverage,
        strategy: formVal.type!
      };

      this.freqtradeService.startBot(input).subscribe({
        next: () => {
          this.isLoading = false;
          this.toaster.success(`Bot iniciado para ${pair}`, 'Motor Activo');
        },
        error: (err) => {
          this.isLoading = false;
          this.toaster.error('Error al iniciar el bot. Verifica la conexión con el servidor Freqtrade.', 'Error de Ejecución');
          console.error(err);
        }
      });
    }
  }
}
