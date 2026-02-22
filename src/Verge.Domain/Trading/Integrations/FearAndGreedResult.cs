using System;

namespace Verge.Trading.Integrations;

public class FearAndGreedResult
{
    public string Name { get; set; } = string.Empty;
    public int Value { get; set; }
    public string ValueClassification { get; set; } = string.Empty;
    public DateTime Timestamp { get; set; }
    public string TimeUntilUpdate { get; set; } = string.Empty;
}
