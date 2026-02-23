using System;

namespace Verge.Trading;

public enum TradingLevel
{
    Beginner,
    Intermediate,
    Advanced,
    Expert
}

public enum RiskTolerance
{
    Low,
    Medium,
    High
}

public enum SignalDirection
{
    Long,
    Short,
    Auto
}

public enum SignalConfidence
{
    High,
    Medium,
    Low
}

public enum TradingStage
{
    Evaluating = 1,
    Prepared = 2,
    BuyActive = 3,
    SellActive = 4
}

public enum AlertType
{
    Stage1,
    Stage2,
    Stage3,
    Stage4,
    Custom,
    System
}

public enum AnalysisLogType
{
    Standard,           // Logs normales del scanner
    OpportunityRanking, // Top 3 oportunidades (solo AUTO)
    AlertContext,       // "Mercado favorable para..."
    AlertPrepare,       // "Preparándose para..."
    AlertEntry,         // "🚀 ENTRAR..."
    AlertInvalidated,   // "❌ Setup invalidado"
    AlertExit           // "💰 Take Profit alcanzado"
}

public enum TradeStatus
{
    Open,
    Win,
    Loss,
    BreakEven,
    Canceled,
    Expired
}

public enum OrderType
{
    Market,
    Limit
}

public enum TradingStyle
{
    Scalping,
    DayTrading,
    SwingTrading,
    PositionTrading,
    HODL,
    GridTrading,
    Arbitrage,
    Algorithmic,
    Auto
}
