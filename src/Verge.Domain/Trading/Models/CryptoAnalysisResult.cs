using System;

namespace Verge.Trading;

public class CryptoAnalysisResult
{
    public string Symbol { get; set; } = string.Empty;
    public decimal Rsi { get; set; }
    public string Trend { get; set; } = "neutral"; // bullish, bearish, lateral
    public decimal VolumeChange { get; set; }
    public string Pattern { get; set; } = "none";
    public int Confidence { get; set; }
    public SignalDirection Signal { get; set; } = SignalDirection.Auto;
    public string Summary { get; set; } = string.Empty;
}
