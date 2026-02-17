using System;
using System.Collections.Generic;

namespace Verge.Trading.DTOs;

public class SentimentAnalysisDto
{
    public string Sentiment { get; set; }
    public float Confidence { get; set; }
    public Dictionary<string, float> Scores { get; set; }
}

public class EnhancedAnalysisDto
{
    public decimal Rsi { get; set; }
    public SentimentAnalysisDto Sentiment { get; set; }
    public string Summary { get; set; }
    public string Recommendation { get; set; }
}
