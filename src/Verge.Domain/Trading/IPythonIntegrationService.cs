using System.Threading.Tasks;
using System.Collections.Generic;

namespace Verge.Trading;

public interface IPythonIntegrationService
{
    Task<SentimentResponseModel> AnalyzeSentimentAsync(string text);
    Task<bool> IsHealthyAsync();
}

public class SentimentResponseModel
{
    public string Sentiment { get; set; }
    public float Confidence { get; set; }
    public Dictionary<string, float> Scores { get; set; }
}
