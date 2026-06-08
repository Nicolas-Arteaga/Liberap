using System;
using System.Collections.Generic;

namespace Verge.Trading.Nexus5;

public class Nexus5ResultDto
{
    public string Symbol { get; set; }
    public string Timeframe { get; set; }
    public DateTime AnalyzedAt { get; set; }
    public double AiConfidence { get; set; }
    public string Direction { get; set; }
    public string Recommendation { get; set; }
    public string Phase { get; set; }
    public double PhaseScore { get; set; }
    public string EntryTimeframe { get; set; }
    public bool CompressionState { get; set; }
    public bool IgnitionDetected { get; set; }
    public bool BypassActive { get; set; }
    public double Next3CandlesProb { get; set; }
    public double Next5CandlesProb { get; set; }
    public double Next10CandlesProb { get; set; }
    public double EstimatedRangePercent { get; set; }
    public string Regime { get; set; }
    public bool VolumeExplosion { get; set; }
    public Nexus5GroupScoresDto GroupScores { get; set; }
    public Nexus5FeaturesDto Features { get; set; }
    public Dictionary<string, string> Detectivity { get; set; }
}

public class Nexus5GroupScoresDto
{
    public double G1PriceAction { get; set; }
    public double G2SmcIct { get; set; }
    public double G3Wyckoff { get; set; }
    public double G4Fractals { get; set; }
    public double G5Volume { get; set; }
    public double G6Ml { get; set; }
}

public class Nexus5FeaturesDto
{
    // G1: Price Action — Ruptura Sniper
    public double CompressionRange { get; set; }
    public bool IgnitionCandle { get; set; }
    public double EfficiencyCheck { get; set; }
    // G2: SMC/ICT — Desplazamiento
    public bool DisplacementFvg { get; set; }
    public bool MicroChoch { get; set; }
    public bool InstantOrderBlock { get; set; }
    // G3: Wyckoff — Fases de Resorte
    public bool CompressionZone { get; set; }
    public bool SosDetected { get; set; }
    public bool JumpingCreek { get; set; }
    // G4: Fractales — Micro-Tendencia
    public bool FractalHighBreak { get; set; }
    public double Ema7Angle { get; set; }
    public bool HhHlSequence { get; set; }
    // G5: Volume & Order Flow
    public double RelativeVolMultiplier { get; set; }
    public double VolIntensity { get; set; }
    public double BuyingImbalance { get; set; }
    // G6: ML — Anomalías
    public double AtrExpansion { get; set; }
    public double ZScore { get; set; }
    public double RsiVelocity { get; set; }

    // ── ESTRUCTURAL ANALYSIS — Reglas de Oro (v8.0) ───────────────────────────
    public double SlopeMa50 { get; set; }
    public double SlopeMa99 { get; set; }
    public bool GravityMa99Safe { get; set; }
    public double VolRatio { get; set; }
    public bool CompressionViper { get; set; }
    public bool Ma50Horizontal { get; set; }
    public double Ma50Ma99Distance { get; set; }
    public double PriceToMa99Pct { get; set; }
}
