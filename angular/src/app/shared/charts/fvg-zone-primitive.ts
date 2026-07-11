import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type {
  ISeriesPrimitive,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  SeriesAttachedParameter,
  Time,
  ISeriesApi,
  IChartApi,
  SeriesType,
} from 'lightweight-charts';

/**
 * Zona FVG lista para dibujar: precio (top/bottom), dirección y SL/TP. El
 * ancho horizontal es siempre fijo (ver MIN_BOX_WIDTH_RATIO) — no depende
 * de cuándo se formó la zona, así se ve igual sin importar la temporalidad
 * del gráfico.
 */
export interface FvgRenderZone {
  top: number;
  bottom: number;
  direction: string; // 'bullish' | 'bearish'
  slPrice: number;
  tpPrice: number;
  isIfvg: boolean;
  sourceInterval: string;
}

// Ancho mínimo visible del rectángulo, como fracción del ancho del gráfico.
// Sin este piso, una zona de ejecución (1m, formada hace 1-3 minutos)
// dibujada sobre un gráfico de 15m/1h mide un par de píxeles — invisible.
// El rango de precio (dónde entrar) sigue siendo el real; solo se extiende
// el borde izquierdo hacia atrás para que se pueda leer.
const MIN_BOX_WIDTH_RATIO = 0.18;

class FvgZonePaneRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly zones: FvgRenderZone[],
    private readonly series: ISeriesApi<SeriesType>,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      for (const zone of this.zones) {
        const yTop = this.series.priceToCoordinate(zone.top);
        const yBottom = this.series.priceToCoordinate(zone.bottom);
        const ySl = this.series.priceToCoordinate(zone.slPrice);
        const yTp = this.series.priceToCoordinate(zone.tpPrice);
        if (yTop === null || yBottom === null || ySl === null || yTp === null) {
          continue; // el precio de la zona está fuera del rango visible del eje
        }

        // Ancho fijo anclado al borde derecho ("ahora"), SIN depender de
        // timeToCoordinate: el timestamp exacto de la vela que formó la zona
        // (por ej. de 1m) no coincide con los bordes de vela de un gráfico
        // en 5m/15m, y timeToCoordinate devuelve null en ese caso — lo que
        // hacía desaparecer la caja al cambiar de temporalidad. La posición
        // horizontal exacta no aporta información real (el dato que importa
        // es el precio), así que se fija un ancho legible siempre.
        const width = mediaSize.width * MIN_BOX_WIDTH_RATIO;
        const xLeftVisible = mediaSize.width - width;
        const isBullish = zone.direction === 'bullish';

        const greenFill = 'rgba(0,255,136,0.16)';
        const redFill = 'rgba(255,68,102,0.16)';
        const zoneFill = 'rgba(0,229,255,0.14)';
        const greenBorder = 'rgba(0,255,136,0.65)';
        const redBorder = 'rgba(255,68,102,0.65)';
        const zoneBorder = 'rgba(0,229,255,0.55)';

        const fillAndStroke = (yA: number, yB: number, fill: string, border: string) => {
          const top = Math.min(yA, yB);
          const height = Math.max(Math.abs(yB - yA), 1);
          context.fillStyle = fill;
          context.fillRect(xLeftVisible, top, width, height);
          context.strokeStyle = border;
          context.lineWidth = 1;
          // Las zonas IFVG (FVG invalidado y dado vuelta) se marcan con
          // borde punteado para distinguirlas de un FVG normal a simple vista.
          context.setLineDash(zone.isIfvg ? [5, 3] : []);
          context.strokeRect(xLeftVisible, top, width, height);
          context.setLineDash([]);
        };

        // Alcista: entra en [bottom,top], TP arriba de top (verde, grande),
        // SL debajo de bottom (rojo, chico). Bajista: al revés.
        if (isBullish) {
          fillAndStroke(yTp, yTop, greenFill, greenBorder);   // TP: por encima del gap
          fillAndStroke(yBottom, ySl, redFill, redBorder);    // SL: por debajo del gap
        } else {
          fillAndStroke(yBottom, yTp, greenFill, greenBorder); // TP: por debajo del gap
          fillAndStroke(ySl, yTop, redFill, redBorder);        // SL: por encima del gap
        }

        // La zona del FVG en sí (la entrada) — resaltada aparte, en el medio.
        fillAndStroke(yTop, yBottom, zoneFill, zoneBorder);

        context.font = '10px monospace';
        context.textBaseline = 'middle';
        const labelX = xLeftVisible + 4;
        context.fillStyle = greenBorder;
        context.fillText(`TP ${zone.tpPrice.toPrecision(6)}`, labelX, isBullish ? yTp + 10 : yBottom - 10);
        context.fillStyle = redBorder;
        context.fillText(`SL ${zone.slPrice.toPrecision(6)}`, labelX, isBullish ? ySl - 10 : yTop + 10);
        context.fillStyle = zoneBorder;
        const zoneLabel = `ENTRADA (${zone.isIfvg ? 'IFVG' : 'FVG'} ${zone.sourceInterval})`;
        context.fillText(zoneLabel, labelX, (yTop + yBottom) / 2);
      }
    });
  }
}

class FvgZonePaneView implements IPrimitivePaneView {
  constructor(private readonly source: FvgZonePrimitive) {}

  renderer(): IPrimitivePaneRenderer | null {
    if (!this.source.chartRef || !this.source.seriesRef) {
      return null;
    }
    return new FvgZonePaneRenderer(this.source.zones, this.source.seriesRef);
  }
}

/**
 * Primitive de lightweight-charts v5 que dibuja las zonas FVG como
 * rectángulos rojo/verde sobre el candlestick. No hay una clase
 * Rectangle/Box nativa en la librería — esto se implementa a mano
 * usando el sistema de primitives (attachPrimitive/ISeriesPrimitive).
 */
export class FvgZonePrimitive implements ISeriesPrimitive<Time> {
  zones: FvgRenderZone[] = [];
  chartRef: IChartApi | null = null;
  seriesRef: ISeriesApi<SeriesType> | null = null;

  private readonly _paneViews: FvgZonePaneView[];
  private _requestUpdate: (() => void) | null = null;

  constructor() {
    this._paneViews = [new FvgZonePaneView(this)];
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chartRef = param.chart as IChartApi;
    this.seriesRef = param.series as ISeriesApi<SeriesType>;
    this._requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.chartRef = null;
    this.seriesRef = null;
    this._requestUpdate = null;
  }

  updateZones(zones: FvgRenderZone[]): void {
    this.zones = zones;
    this._requestUpdate?.();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this._paneViews;
  }
}
