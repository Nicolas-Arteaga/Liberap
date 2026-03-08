using System;
using System.Collections.Generic;

namespace Verge.Trading;

public class WalkForwardReportDto
{
    public DateTime EvaluationDate { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public string TradingStyle { get; set; } = string.Empty;
    public List<WalkForwardWindowDto> Windows { get; set; } = new();
    
    // Institutuional Criteria
    public bool PassedAllWindows { get; set; }
}

public class WalkForwardWindowDto
{
    public string WindowName { get; set; } = string.Empty; // e.g. "2019-2021"
    public DateTime TrainingStart { get; set; }
    public DateTime TrainingEnd { get; set; }
    public DateTime TestingStart { get; set; }
    public DateTime TestingEnd { get; set; }
    
    public BacktestResultDto TrainingResult { get; set; } = new();
    public BacktestResultDto TestingResult { get; set; } = new();
    
    public bool PassedProfitFactor => TestingResult.ProfitFactor > 1.5;
}

public class MonteCarloReportDto
{
    public DateTime EvaluationDate { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public int Iterations { get; set; } = 10000;
    public decimal InitialCapital { get; set; } = 1000m;
    
    public decimal AverageEndingCapital { get; set; }
    public decimal WorstCaseDrawdown { get; set; } // 5th Percentile
    public double ProbabilityOfRuin { get; set; } // % of iterations where capital hit 0 or crossed ruin threshold

    // Criteria
    public bool PassedRuinRisk => ProbabilityOfRuin < 0.01; // < 1%
}

public class StressTestReportDto
{
    public DateTime EvaluationDate { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public List<StressTestEventDto> Events { get; set; } = new();
    
    public bool PassedAllEvents { get; set; }
}

public class StressTestEventDto
{
    public string EventName { get; set; } = string.Empty; // e.g. "COVID Crash (March 2020)"
    public DateTime StartDate { get; set; }
    public DateTime EndDate { get; set; }
    public BacktestResultDto Result { get; set; } = new();
    
    // Criteria: Max Drawdown < 40%
    public bool Survived => Result.MaxDrawdown < 0.40m;
}
