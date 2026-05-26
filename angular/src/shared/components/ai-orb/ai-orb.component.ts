import { Component, OnInit, OnDestroy, AfterViewInit, ViewChild, ElementRef, inject, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import * as THREE from 'three';

@Component({
  selector: 'app-ai-orb',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div #orbContainer class="ai-orb-container"></div>
  `,
  styleUrls: ['./ai-orb.component.scss']
})
export class AiOrbComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('orbContainer', { static: false }) orbContainer!: ElementRef<HTMLDivElement>;
  
  private ngZone = inject(NgZone);
  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private renderer!: THREE.WebGLRenderer;
  private particles!: THREE.Points;
  private animationFrameId: number | null = null;
  private resizeListener?: () => void;

  ngOnInit(): void {}

  ngAfterViewInit(): void {
    setTimeout(() => {
      this.ngZone.runOutsideAngular(() => {
        this.initThreeJS();
      });
    }, 100);
  }

  ngOnDestroy(): void {
    if (this.animationFrameId) cancelAnimationFrame(this.animationFrameId);
    if (this.resizeListener) window.removeEventListener('resize', this.resizeListener);
    if (this.renderer) this.renderer.dispose();
  }

  private initThreeJS(): void {
    if (!this.orbContainer?.nativeElement) return;

    const container = this.orbContainer.nativeElement;
    const width = 120;
    const height = 120;

    console.log('AI Orb: Initializing Three.js', { width, height, container });

    // Scene with dark background
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x050816);

    // Camera
    this.camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 100);
    this.camera.position.z = 4;

    // Renderer
    this.renderer = new THREE.WebGLRenderer({ 
      antialias: true,
      alpha: false
    });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(this.renderer.domElement);

    console.log('AI Orb: Canvas created', this.renderer.domElement);

    // Create particle sphere
    this.createParticleSphere();

    console.log('AI Orb: Particle sphere created');

    // Resize handler
    this.resizeListener = () => this.onResize();
    window.addEventListener('resize', this.resizeListener);

    // Start animation
    this.animate();
  }

  private createParticleSphere(): void {
    const particleCount = 100;
    const geometry = new THREE.BufferGeometry();
    
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);

    const colorPalette = [
      new THREE.Color(0x00f3ff),
      new THREE.Color(0x0088ff),
      new THREE.Color(0xffffff),
      new THREE.Color(0x00ff88),
    ];

    for (let i = 0; i < particleCount; i++) {
      const phi = Math.acos(-1 + (2 * i) / particleCount);
      const theta = Math.sqrt(particleCount * Math.PI) * phi;
      
      const radius = 1.2 + Math.random() * 0.2;
      
      positions[i * 3] = radius * Math.cos(theta) * Math.sin(phi);
      positions[i * 3 + 1] = radius * Math.sin(theta) * Math.sin(phi);
      positions[i * 3 + 2] = radius * Math.cos(phi);

      const color = colorPalette[Math.floor(Math.random() * colorPalette.length)];
      colors[i * 3] = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
      size: 0.05,
      vertexColors: true,
      transparent: true,
      opacity: 0.8,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true
    });

    this.particles = new THREE.Points(geometry, material);
    this.scene.add(this.particles);
    
    console.log('AI Orb: Particles created with basic material', this.particles);
  }

  private onResize(): void {
    if (!this.orbContainer?.nativeElement) return;
    const width = 120;
    const height = 120;

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  private animate = (): void => {
    this.animationFrameId = requestAnimationFrame(this.animate);

    const time = performance.now() * 0.001;

    if (this.particles) {
      this.particles.rotation.y += 0.003;
      this.particles.rotation.x += 0.0015;
    }

    this.renderer.render(this.scene, this.camera);
  };
}
