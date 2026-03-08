using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Verge.Trading;

namespace Verge.Trading.DecisionEngine;

public interface ITradingDecisionEngine
{
    Task<DecisionResult> EvaluateAsync(
        TradingSession session, 
        TradingStyle style, 
        MarketContext context, 
        bool isAutoMode = false,
        Dictionary<string, float>? weightOverrides = null,
        int? entryThresholdOverride = null,
        float? trailingMultiplierOverride = null);
}
