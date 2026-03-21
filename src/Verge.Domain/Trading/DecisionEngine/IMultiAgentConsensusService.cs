using System.Collections.Generic;
using System.Threading.Tasks;

namespace Verge.Trading.DecisionEngine;

public interface IMultiAgentConsensusService
{
    Task<AgentConsensusResult> GetConsensusAsync(MarketContext context, TradingStyle style);
}

public class AgentConsensusResult
{
    public float Score { get; set; } // 0-100
    public string Reasoning { get; set; } = string.Empty;
    public Dictionary<string, string> AgentOpinions { get; set; } = new();
}
