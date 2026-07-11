import {
  Component,
  Input,
  ViewChild,
  ElementRef,
  AfterViewInit,
  OnDestroy,
  OnChanges,
  SimpleChanges,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { VolumeProfileBinDto } from '../../proxy/trading/fvg/models';

/**
 * Volume profile vertical — no existe nada nativo en lightweight-charts
 * para esto (solo HistogramSeries horizontal, por tiempo). Es un <canvas>
 * aparte, posicionado por CSS a la izquierda del gráfico, que se mantiene
 * alineado en Y usando la misma función priceToCoordinate() de la serie
 * de velas del gráfico principal.
 */
@Component({
  selector: 'app-volume-profile-sidebar',
  standalone: true,
  imports: [CommonModule],
  template: `<canvas #canvas class="vp-canvas"></canvas>`,
  styleUrls: ['./volume-profile-sidebar.component.scss'],
})
export class VolumeProfileSidebarComponent implements AfterViewInit, OnDestroy, OnChanges {
  @Input() bins: VolumeProfileBinDto[] = [];
  @Input() priceToCoordinate: ((price: number) => number | null) | null = null;
  @Input() heightPx = 500;

  @ViewChild('canvas', { static: true }) canvasRef!: ElementRef<HTMLCanvasElement>;

  private resizeObserver: ResizeObserver | null = null;

  ngAfterViewInit(): void {
    this.resizeObserver = new ResizeObserver(() => this.render());
    this.resizeObserver.observe(this.canvasRef.nativeElement.parentElement ?? this.canvasRef.nativeElement);
    this.render();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (this.canvasRef) {
      this.render();
    }
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
  }

  render(): void {
    const canvas = this.canvasRef?.nativeElement;
    if (!canvas || !this.priceToCoordinate) {
      return;
    }

    const parent = canvas.parentElement;
    const width = parent?.clientWidth || 140;
    const height = parent?.clientHeight || this.heightPx;
    const dpr = window.devicePixelRatio || 1;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    if (!this.bins || this.bins.length === 0) {
      return;
    }

    const maxVolume = Math.max(...this.bins.map(b => b.volume), 1);

    for (const bin of this.bins) {
      const yTop = this.priceToCoordinate(bin.priceHigh);
      const yBottom = this.priceToCoordinate(bin.priceLow);
      if (yTop === null || yBottom === null) {
        continue;
      }

      const barWidth = Math.max((bin.volume / maxVolume) * width, 1);
      const color = bin.isPoc
        ? 'rgba(0, 229, 255, 0.95)'
        : bin.isHvn
          ? 'rgba(0, 229, 255, 0.55)'
          : 'rgba(0, 229, 255, 0.22)';

      ctx.fillStyle = color;
      ctx.fillRect(width - barWidth, Math.min(yTop, yBottom), barWidth, Math.max(Math.abs(yBottom - yTop), 1));
    }
  }
}
