using Verge.Trading;

namespace Verge.Trading.DecisionEngine;

public interface ITradingDecisionEngine
{
    DecisionResult Evaluate(TradingSession session, TradingStyle style, MarketContext context);
}
