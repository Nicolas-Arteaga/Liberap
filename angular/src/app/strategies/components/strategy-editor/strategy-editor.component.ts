import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { StrategyProfileService } from '../../services/strategy-profile.service';
import { CreateUpdateStrategyProfileDto } from '../../../proxy/trading/dtos/models';
import { IonIcon } from '@ionic/angular/standalone';
import { finalize } from 'rxjs/operators';

type MaTarget = 'ma7' | 'ma25' | 'ma50' | 'ma99';
type OrderRule = 'less' | 'greater' | null;
type SlopeOp = 'gte' | 'lte' | null;

export interface MaPatternParams {
  timeframe: '1m' | '5m' | '15m' | '1h';
  order: { ma7VsMa25: OrderRule; ma7VsMa50: OrderRule; ma7VsMa99: OrderRule };
  slope: {
    targetMa: MaTarget; windowCandles: number;
    currentOp: SlopeOp; currentDeg: number | null;
    priorOp: SlopeOp; priorDeg: number | null;
  };
  touch: {
    enabled: boolean; targetMa: MaTarget; tolerancePct: number;
    side: 'fromBelow' | 'fromAbove'; requireCloseStaysOriginalSide: boolean;
  };
  distanceBetweenMas: { enabled: boolean; maA: MaTarget; maB: MaTarget; maxPct: number };
  contextSlope: { enabled: boolean; targetMa: MaTarget; windowCandles: number; op: 'gte' | 'lte'; deg: number };
  peakProximity: { enabled: boolean; type: 'recentHigh' | 'recentLow'; lookbackCandles: number; tolerancePct: number };
  exit: { slReference: 'recentLow' | 'recentHigh'; slLookbackCandles: number; slBufferPct: number; tpMinPct: number };
}

function defaultPatternParams(): MaPatternParams {
  return {
    timeframe: '1h',
    order: { ma7VsMa25: null, ma7VsMa50: null, ma7VsMa99: null },
    slope: { targetMa: 'ma7', windowCandles: 3, currentOp: null, currentDeg: null, priorOp: null, priorDeg: null },
    touch: { enabled: false, targetMa: 'ma25', tolerancePct: 0.3, side: 'fromBelow', requireCloseStaysOriginalSide: true },
    distanceBetweenMas: { enabled: false, maA: 'ma7', maB: 'ma99', maxPct: 0.5 },
    contextSlope: { enabled: false, targetMa: 'ma99', windowCandles: 12, op: 'gte', deg: 0 },
    peakProximity: { enabled: false, type: 'recentHigh', lookbackCandles: 10, tolerancePct: 1.0 },
    exit: { slReference: 'recentLow', slLookbackCandles: 10, slBufferPct: 1.0, tpMinPct: 8.0 },
  };
}

/**
 * Parámetros del patrón de Compresión ADN — deliberadamente mínimos: la
 * detección (compresión + cruces de MA7 + ignición) vive entera en el
 * python-service (mismo endpoint que usa el radar /adn-compression), acá
 * solo se elige qué temporalidad escanea este perfil. LONG-only por ahora
 * (ver decisión con Nico: validar en una sola dirección antes de sumar short).
 */
export interface AdnCompressionParams {
  timeframe: '5m' | '1d';
}

function defaultAdnParams(): AdnCompressionParams {
  return { timeframe: '5m' };
}

/**
 * Parámetros del patrón FVG — igual de mínimos: la detección (3 velas del
 * gap, SL/TP estructurales) vive entera en python-service (mismo
 * /fvg/scan que usa el radar, con sort_by=range en vez de score). Acá solo
 * se elige la temporalidad (1m/5m/15m). Soporta LONG y SHORT — la propia
 * zona define la dirección (bullish/bearish), no hace falta forzar un lado.
 */
export interface FvgPatternParams {
  timeframe: '1m' | '5m' | '15m';
  // Filtro de agotamiento (opt-in, default apagado — no afecta a los
  // perfiles FVG existentes). Auditoría real 2026-07-22 sobre FVG-15m:
  // los SHORT que entran contra una subida previa fuertemente parabólica
  // (pendiente de EMA50 pronunciada) dieron 29.2% win rate / +$46.40,
  // contra 13.6%/-$7.52 sin ese filtro — ese 15% de los trades generó el
  // 65% de toda la ganancia. Ver agent/verge_agent.py::_build_fvg_candidate.
  requireExhaustion?: boolean;
  minExhaustionSlopeDeg?: number;
}

function defaultFvgParams(): FvgPatternParams {
  return { timeframe: '5m', requireExhaustion: false, minExhaustionSlopeDeg: 3.0 };
}

@Component({
  selector: 'app-strategy-editor',
  standalone: true,
  imports: [CommonModule, FormsModule, IonIcon],
  templateUrl: './strategy-editor.component.html',
  styleUrls: ['./strategy-editor.component.scss']
})
export class StrategyEditorComponent implements OnInit {
  private service = inject(StrategyProfileService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  id: string | null = null;
  isLoading = false;
  activeTab: 'identity' | 'filters' | 'risk' | 'advanced' | 'pattern' | 'preview' = 'identity';

  model: CreateUpdateStrategyProfileDto = {
    name: '',
    description: '',
    color: '#00C47D',
    isActive: true,
    minConfluenceScore: 50,
    minNexusConfidence: 70,
    maxRsiLong: 80,
    minRsiShort: 20,
    maxMa7DistancePct: 3.5,
    allowedSources: 'Nexus,Nexus5,LSE,Bridge',
    allowLong: true,
    allowShort: true,
    marginPerTrade: 150,
    tpMultiplier: 3.0,
    slMultiplier: 0.8,
    minRR: 1.5,
    maxOpenPositions: 3,
    maxTradeDurationCandles: 8,
    extremeRsiVeto: true,
    enabledDays: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    maxEntrySlippagePct: 0.002,
    lseMaxEntrySlippagePct: 0.015,
    minTpDistancePct: 0.003,
    minSlDistancePct: 0.002,
    minEstimatedRangePct: 3.0,
    maxNexusSignalAgeSeconds: 120,
    nexusMaxPriceDriftPct: 0.025,
    strategyType: 'Generic',
    patternParamsJson: undefined,
    broadcastToBinance: false,
  };

  /**
   * Parámetros del motor de patrones de medias móviles — separado del
   * `model` plano porque es un objeto anidado; se serializa/deserializa
   * a/desde `model.patternParamsJson` al guardar/cargar.
   */
  patternParams: MaPatternParams = defaultPatternParams();
  adnParams: AdnCompressionParams = defaultAdnParams();
  fvgParams: FvgPatternParams = defaultFvgParams();

  readonly maOptions: { value: MaTarget; label: string }[] = [
    { value: 'ma7', label: 'MA7' },
    { value: 'ma25', label: 'MA25' },
    { value: 'ma50', label: 'MA50' },
    { value: 'ma99', label: 'MA99' },
  ];

  get isMaGeometry(): boolean {
    return this.model.strategyType === 'MaGeometry';
  }

  get isAdnCompression(): boolean {
    return this.model.strategyType === 'AdnCompression';
  }

  get isFvgStrategy(): boolean {
    return this.model.strategyType === 'FVG';
  }

  /** Cualquier estrategia de patrón (bypassea el motor de Nexus/confluencia genérico). */
  get isPatternStrategy(): boolean {
    return this.isMaGeometry || this.isAdnCompression || this.isFvgStrategy;
  }

  ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id');
    if (this.id) {
      this.loadProfile(this.id);
    }
  }

  loadProfile(id: string) {
    this.isLoading = true;
    this.service.getById(id)
      .pipe(finalize(() => this.isLoading = false))
      .subscribe(data => {
        this.model = { ...data };
        if (data.patternParamsJson) {
          try {
            this.patternParams = { ...defaultPatternParams(), ...JSON.parse(data.patternParamsJson) };
            this.adnParams = { ...defaultAdnParams(), ...JSON.parse(data.patternParamsJson) };
            this.fvgParams = { ...defaultFvgParams(), ...JSON.parse(data.patternParamsJson) };
          } catch {
            this.patternParams = defaultPatternParams();
            this.adnParams = defaultAdnParams();
            this.fvgParams = defaultFvgParams();
          }
        } else {
          this.patternParams = defaultPatternParams();
          this.adnParams = defaultAdnParams();
          this.fvgParams = defaultFvgParams();
        }
      });
  }

  onStrategyTypeChange(type: string) {
    this.model.strategyType = type;
    if (type === 'MaGeometry') {
      // Un patrón de medias no ambiguo necesita una dirección fija — no "Automático".
      if (this.model.allowLong && this.model.allowShort) {
        this.model.allowLong = true;
        this.model.allowShort = false;
      }
      this.activeTab = 'pattern';
    } else if (type === 'AdnCompression') {
      // LONG-only por ahora — ver AdnCompressionParams.
      this.model.allowLong = true;
      this.model.allowShort = false;
    }
    // FVG: sin forzar dirección — la propia zona (bullish/bearish) define
    // LONG o SHORT, "Automático" (el default) queda bien acá.
  }

  save() {
    if (!this.model.name) {
      alert('El nombre es obligatorio');
      return;
    }

    if (this.isMaGeometry) {
      if (this.model.allowLong === this.model.allowShort) {
        alert('Un perfil de Patrón de Medias necesita elegir "Solo Long" o "Solo Short" en Identidad (no "Automático").');
        return;
      }
      this.model.patternParamsJson = JSON.stringify(this.patternParams);
    } else if (this.isAdnCompression) {
      this.model.patternParamsJson = JSON.stringify(this.adnParams);
    } else if (this.isFvgStrategy) {
      this.model.patternParamsJson = JSON.stringify(this.fvgParams);
    } else {
      this.model.patternParamsJson = undefined;
    }

    const obs = this.id
      ? this.service.update(this.id, this.model)
      : this.service.create(this.model);

    obs.subscribe(() => {
      this.router.navigate(['/strategies']);
    });
  }

  cancel() {
    this.router.navigate(['/strategies']);
  }

  resetToDefaults() {
    if (confirm('¿Restablecer todos los valores a los parámetros por defecto?')) {
      // Logic to reset based on current tab or all
      if (this.activeTab === 'filters') {
         this.model.minConfluenceScore = 50;
         this.model.minNexusConfidence = 70;
         this.model.maxRsiLong = 80;
         this.model.minRsiShort = 20;
      } else if (this.activeTab === 'risk') {
         this.model.marginPerTrade = 150;
         this.model.tpMultiplier = 3.0;
         this.model.slMultiplier = 0.8;
      } else if (this.activeTab === 'pattern') {
         this.patternParams = defaultPatternParams();
      }
      // etc...
    }
  }

  isSourceAllowed(source: string): boolean {
    if (!this.model.allowedSources) return false;
    return this.model.allowedSources.split(',').includes(source);
  }

  toggleSource(source: string) {
    let sources = this.model.allowedSources ? this.model.allowedSources.split(',') : [];
    const index = sources.indexOf(source);
    if (index > -1) {
      sources.splice(index, 1);
    } else {
      sources.push(source);
    }
    this.model.allowedSources = sources.join(',');
  }
}
