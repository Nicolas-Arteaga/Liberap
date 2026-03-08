using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Volo.Abp.DependencyInjection;
using Volo.Abp.Domain.Services;

namespace Verge.Trading.Optimization;

public class OptimizationService : DomainService, ITransientDependency
{
    private readonly ILogger<OptimizationService> _logger;

    public OptimizationService(ILogger<OptimizationService> logger)
    {
        _logger = logger;
    }

    public List<Dictionary<string, float>> GenerateWeightPermutations()
    {
        var permutations = new List<Dictionary<string, float>>();
        float step = 0.05f;

        // Using loops for the 5 factor weights
        for (float tech = 0.1f; tech <= 0.5f; tech += step)
        {
            for (float flow = 0.1f; flow <= 0.4f; flow += step)
            {
                for (float liq = 0.1f; liq <= 0.4f; liq += step)
                {
                    for (float whales = 0.0f; whales <= 0.3f; whales += step)
                    {
                        for (float macro = 0.0f; macro <= 0.2f; macro += step)
                        {
                            // Validate sum is 1.0 (with small tolerance for float precision)
                            float sum = tech + flow + liq + whales + macro;
                            if (Math.Abs(sum - 1.0f) < 0.001f)
                            {
                                permutations.Add(new Dictionary<string, float>
                                {
                                    { "Technical", (float)Math.Round(tech, 2) },
                                    { "Quantitative", (float)Math.Round(flow, 2) }, // Order Flow
                                    { "Sentiment", (float)Math.Round(liq, 2) },     // Liquidations
                                    { "Fundamental", (float)Math.Round(macro, 2) }, // Macro/News
                                    { "Whales", (float)Math.Round(whales, 2) }
                                });
                            }
                        }
                    }
                }
            }
        }

        return permutations;
    }

    public (double ProfitFactor, double Sharpe, double WinRate) CalculateAdvancedMetrics(int totalTrades, int wins, decimal totalPnL)
    {
        if (totalTrades == 0) return (0, 0, 0);

        double winRate = (double)wins / totalTrades * 100;
        
        // Refined Profit Factor proxy
        // Ideally we'd use: Gross Profit / Gross Loss
        // For this optimization phase we use a simplified PnL-based scaling
        double profitFactor = totalPnL > 0 ? 1.0 + (double)totalPnL / 500.0 : 0.5; 
        double sharpe = profitFactor * 0.7; // Proxy for risk-adjusted return

        return (profitFactor, sharpe, winRate);
    }
}
