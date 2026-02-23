using System;
using Verge.Trading.DecisionEngine.Profiles;

namespace Verge.Trading.DecisionEngine.Factory;

public static class TradingStyleProfileFactory
{
    public static ITradingStyleProfile GetProfile(TradingStyle style)
    {
        return style switch
        {
            TradingStyle.Scalping => new ScalpingProfile(),
            TradingStyle.DayTrading => new DayTradingProfile(),
            TradingStyle.SwingTrading => new SwingTradingProfile(),
            TradingStyle.PositionTrading => new PositionTradingProfile(),
            TradingStyle.GridTrading => new GridTradingProfile(),
            TradingStyle.HODL => new HodlProfile(),
            _ => new DefaultProfile()
        };
    }
}
