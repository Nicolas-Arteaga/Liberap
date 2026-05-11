import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { StrategyProfileService } from '../../services/strategy-profile.service';
import { GlassButtonComponent } from '../../../../shared/components/glass-button/glass-button.component';
import { CardContentComponent } from '../../../../shared/components/card-content/card-content.component';
import { IonIcon } from '@ionic/angular/standalone';

@Component({
  selector: 'app-strategy-performance',
  standalone: true,
  imports: [CommonModule, GlassButtonComponent, CardContentComponent, IonIcon],
  templateUrl: './strategy-performance.component.html',
  styleUrls: ['./strategy-performance.component.scss']
})
export class StrategyPerformanceComponent implements OnInit {
  private service = inject(StrategyProfileService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  id: string | null = null;
  performance: any = null;
  isLoading = false;

  ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id');
    if (this.id) {
      this.loadPerformance(this.id);
    }
  }

  loadPerformance(id: string) {
    this.isLoading = true;
    this.service.getPerformance(id).subscribe(data => {
      this.performance = data;
      this.isLoading = false;
    });
  }

  goBack() {
    this.router.navigate(['/strategies']);
  }
}
