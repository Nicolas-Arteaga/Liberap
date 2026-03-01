// alerts.types.ts
// Usamos string literals para emular los enums de la app o si ya están exportados desde los proxies, usaríamos esos.

export interface VergeAlert {
    id: string;
    type: string;
    title: string;
    message: string;
    timestamp: Date;
    read: boolean;

    crypto?: string;
    price?: number;
    confidence?: number;
    direction?: number;
    stage?: number;
    targetZone?: { low: number; high: number };
    score?: number;

    // Institutional 1%
    riskRewardRatio?: number;
    winProbability?: number;

    severity: string;
    icon: string;
}
