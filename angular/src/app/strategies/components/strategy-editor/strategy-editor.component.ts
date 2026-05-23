import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { StrategyProfileService } from '../../services/strategy-profile.service';
import { CreateUpdateStrategyProfileDto } from '../../../proxy/trading/dtos/models';
import { IonIcon } from '@ionic/angular/standalone';
import { finalize } from 'rxjs/operators';

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
  activeTab: 'identity' | 'filters' | 'risk' | 'advanced' | 'preview' = 'identity';

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
    allowedSources: 'Nexus,LSE,Bridge',
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
    nexusMaxPriceDriftPct: 0.025
  };

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
      });
  }

  save() {
    if (!this.model.name) {
      alert('El nombre es obligatorio');
      return;
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
