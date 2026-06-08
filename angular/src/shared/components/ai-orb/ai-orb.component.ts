import { Component, OnInit, AfterViewInit, ViewChild, ElementRef, inject, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-ai-orb',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="ai-orb-container">
      <canvas #aiCanvas></canvas>
    </div>
  `,
  styleUrls: ['./ai-orb.component.scss']
})
export class AiOrbComponent implements OnInit, AfterViewInit {
  @ViewChild('aiCanvas', { static: false }) aiCanvas!: ElementRef<HTMLCanvasElement>;

  private ngZone = inject(NgZone);
  private canvas!: HTMLCanvasElement;
  private ctx!: CanvasRenderingContext2D;
  private animationFrameId: number | null = null;
  private dots: any[] = [];
  private rings: any[] = [];
  private angleX = 0;
  private angleY = 0;
  private pulsePos = 0;
  private taskInterval?: number;

  ngOnInit(): void {}

  ngAfterViewInit(): void {
    setTimeout(() => {
      this.ngZone.runOutsideAngular(() => {
        this.initCanvas();
      });
    }, 100);
  }

  ngOnDestroy(): void {
    if (this.animationFrameId) cancelAnimationFrame(this.animationFrameId);
    if (this.taskInterval) clearInterval(this.taskInterval);
  }

  private initCanvas(): void {
    if (!this.aiCanvas?.nativeElement) return;

    this.canvas = this.aiCanvas.nativeElement;
    this.ctx = this.canvas.getContext('2d')!;

    // Set canvas size - EXACT same as original HTML (800x800)
    this.canvas.width = 800;
    this.canvas.height = 800;

    // Orb configuration - EXACT same as original
    const numDots = 900;
    const radius = 220;

    // Generate Fibonacci sphere dots for uniform distribution - EXACT same as original
    for (let i = 0; i < numDots; i++) {
      const phi = Math.acos(1 - 2 * (i + 0.5) / numDots);
      const theta = Math.PI * (1 + Math.sqrt(5)) * i;
      
      this.dots.push({
        x: radius * Math.sin(phi) * Math.cos(theta),
        y: radius * Math.sin(phi) * Math.sin(theta),
        z: radius * Math.cos(phi),
        baseSize: 1.2 + Math.random() * 1.8
      });
    }

    // Generate orbiting rings around the orb - EXACT same as original
    for (let r = 0; r < 3; r++) {
      const ringRadius = 260 + r * 35;
      const inclination = (r * Math.PI) / 3.5;
      const ringDots: any[] = [];
      const numRingDots = 80 + r * 30;
      
      for (let i = 0; i < numRingDots; i++) {
        ringDots.push({
          angle: (i / numRingDots) * Math.PI * 2,
          radius: ringRadius,
          inclination: inclination,
          speed: 0.015 + r * 0.008
        });
      }
      this.rings.push(ringDots);
    }

    this.pulsePos = -radius - 50;

    // Start animation
    this.animate();
  }

  private rotate(x: number, y: number, z: number, ax: number, ay: number) {
    // Rotate around X axis - EXACT same as original
    let y1 = y * Math.cos(ax) - z * Math.sin(ax);
    let z1 = y * Math.sin(ax) + z * Math.cos(ax);
    // Rotate around Y axis - EXACT same as original
    let x2 = x * Math.cos(ay) + z1 * Math.sin(ay);
    let z2 = -x * Math.sin(ay) + z1 * Math.cos(ay);
    return { x: x2, y: y1, z: z2 };
  }

  private animate = (): void => {
    this.animationFrameId = requestAnimationFrame(this.animate);

    if (!this.ctx || !this.canvas) return;

    // Clear canvas (transparent to show menu background)
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // Update rotation - EXACT same as original
    this.angleX += 0.004;
    this.angleY += 0.008;
    
    // Move pulse across the Y axis - EXACT same as original
    const pulseSpeed = 2.5;
    const pulseWidth = 70;
    this.pulsePos += pulseSpeed;
    if (this.pulsePos > 220 + pulseWidth) {
      this.pulsePos = -220 - pulseWidth;
    }

    const centerX = this.canvas.width / 2;
    const centerY = this.canvas.height / 2;
    const perspective = 700;
    const renderList: any[] = [];

    // Process main sphere dots - EXACT same as original
    for (const dot of this.dots) {
      const rotated = this.rotate(dot.x, dot.y, dot.z, this.angleX, this.angleY);
      const scale = perspective / (perspective + rotated.z);
      const x2d = rotated.x * scale + centerX;
      const y2d = rotated.y * scale + centerY;
      
      // Calculate pulse intersection - EXACT same as original
      const distToPulse = Math.abs(rotated.y - this.pulsePos);
      let pulseFactor = 0;
      if (distToPulse < pulseWidth) {
        pulseFactor = 1 - (distToPulse / pulseWidth);
      }

      const size = dot.baseSize * scale + pulseFactor * 3.5;
      const alpha = Math.min(1, (0.2 + pulseFactor * 0.8) * scale);
      
      renderList.push({
        x: x2d,
        y: y2d,
        z: rotated.z,
        size: size,
        alpha: alpha,
        isPulse: pulseFactor > 0.3
      });
    }

    // Process orbiting ring dots - EXACT same as original
    for (const ring of this.rings) {
      for (const dot of ring) {
        dot.angle += dot.speed;
        const x = dot.radius * Math.cos(dot.angle);
        const y = dot.radius * Math.sin(dot.angle) * Math.sin(dot.inclination);
        const z = dot.radius * Math.sin(dot.angle) * Math.cos(dot.inclination);
        
        const rotated = this.rotate(x, y, z, this.angleX, this.angleY);
        const scale = perspective / (perspective + rotated.z);
        const x2d = rotated.x * scale + centerX;
        const y2d = rotated.y * scale + centerY;

        const distToPulse = Math.abs(rotated.y - this.pulsePos);
        let pulseFactor = 0;
        if (distToPulse < pulseWidth) {
          pulseFactor = 1 - (distToPulse / pulseWidth);
        }

        const size = (1.5 + pulseFactor * 2.5) * scale;
        const alpha = Math.min(1, (0.3 + pulseFactor * 0.7) * scale);

        renderList.push({
          x: x2d,
          y: y2d,
          z: rotated.z,
          size: size,
          alpha: alpha,
          isPulse: pulseFactor > 0.3
        });
      }
    }

    // Sort by Z depth (Painter's Algorithm) - EXACT same as original
    renderList.sort((a, b) => b.z - a.z);

    // Render all points - EXACT same as original
    for (const item of renderList) {
      this.ctx.beginPath();
      this.ctx.arc(item.x, item.y, item.size, 0, Math.PI * 2);
      
      if (item.isPulse) {
        this.ctx.fillStyle = `rgba(150, 255, 255, ${item.alpha})`;
        this.ctx.shadowBlur = 15;
        this.ctx.shadowColor = '#00f0ff';
      } else {
        this.ctx.fillStyle = `rgba(0, 200, 255, ${item.alpha})`;
        this.ctx.shadowBlur = 0;
      }
      this.ctx.fill();
    }
    
    // Reset shadow for next frame - EXACT same as original
    this.ctx.shadowBlur = 0;
  };
}
