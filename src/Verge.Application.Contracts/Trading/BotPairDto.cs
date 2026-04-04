using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Verge.Trading;

public class BotPairDto
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; set; }

    [JsonPropertyName("score")]
    public double Score { get; set; }

    [JsonPropertyName("prediction")]
    public double Prediction { get; set; }

    [JsonPropertyName("bias")]
    public string Bias { get; set; }

    [JsonPropertyName("atr")]
    public double Atr { get; set; }

    [JsonPropertyName("recommendedAction")]
    public string RecommendedAction { get; set; }
}
