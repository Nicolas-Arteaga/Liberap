using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Domain.Services;

namespace Verge.Trading.DecisionEngine;

public class WhaleTrackerService : DomainService, IWhaleTrackerService
{
    private readonly IRepository<WhaleMovement, Guid> _whaleMovementRepository;
    private readonly ILogger<WhaleTrackerService> _logger;

    public WhaleTrackerService(
        IRepository<WhaleMovement, Guid> whaleMovementRepository,
        ILogger<WhaleTrackerService> logger)
    {
        _whaleMovementRepository = whaleMovementRepository;
        _logger = logger;
    }

    public async Task<WhaleAnalysisResult> GetWhaleActivityAsync(string symbol)
    {
        var query = await _whaleMovementRepository.GetQueryableAsync();
        var recentMovements = query
            .Where(m => m.Symbol == symbol && m.Timestamp >= DateTime.UtcNow.AddHours(-24))
            .OrderByDescending(m => m.Timestamp)
            .ToList();

        if (!recentMovements.Any())
        {
            return new WhaleAnalysisResult
            {
                Symbol = symbol,
                NetFlowScore = 0,
                Summary = "No recent whale activity detected."
            };
        }

        double netFlow = 0;
        foreach (var m in recentMovements)
        {
            double multiplier = m.MovementType == "Inflow" || m.MovementType == "Accumulation" ? 1.0 : -1.0;
            netFlow += (double)m.Amount * multiplier * m.InfluenceScore;
        }

        // Normalize NetFlowScore to -1.0 to 1.0
        double normalizedScore = Math.Clamp(netFlow / 1000000.0, -1.0, 1.0); // Simple normalization

        return new WhaleAnalysisResult
        {
            Symbol = symbol,
            NetFlowScore = normalizedScore,
            RecentSignals = recentMovements.Take(5).Select(m => new WhaleSignal
            {
                WalletAddress = m.WalletAddress,
                Amount = m.Amount,
                Type = m.MovementType,
                InfluenceScore = m.InfluenceScore,
                Timestamp = m.Timestamp
            }).ToList(),
            MaxInfluenceDetected = recentMovements.Max(m => m.InfluenceScore),
            Summary = $"Whale Sentiment: {(normalizedScore > 0 ? "Accumulation" : "Distribution")} (Score: {normalizedScore:F2})"
        };
    }

    public async Task ProcessExternalMovementsAsync()
    {
        // SIMULATION: In a real scenario, this would poll Whale Alert API or Etherscan
        // For Sprint 5 development, we generate some mock movements for testing.
        _logger.LogInformation("🌊 Syncing External Whale Movements (Simulated)...");

        var mockWhales = new[]
        {
            new { Symbol = "BTC", Address = "bc1qwhale1", Amount = 1500m, Type = "Accumulation" },
            new { Symbol = "ETH", Address = "0xwhale2", Amount = 50000m, Type = "Inflow" },
            new { Symbol = "SOL", Address = "solwhale3", Amount = 200000m, Type = "Distribution" }
        };

        foreach (var whale in mockWhales)
        {
            // Only add if doesn't exist recently to avoid spam
            var query = await _whaleMovementRepository.GetQueryableAsync();
            if (!query.Any(m => m.WalletAddress == whale.Address && m.Timestamp > DateTime.UtcNow.AddMinutes(-30)))
            {
                var influence = await GetInfluenceScoreAsync(whale.Address);
                var movement = new WhaleMovement(Guid.NewGuid(), whale.Symbol, whale.Address, whale.Amount, 10000, whale.Type)
                {
                    InfluenceScore = influence
                };
                await _whaleMovementRepository.InsertAsync(movement);
                _logger.LogInformation("🐋 NEW WHALE DETECTED: {Address} moved {Amount} {Symbol} ({Type})", whale.Address, whale.Amount, whale.Symbol, whale.Type);
            }
        }
    }

    public async Task<double> GetInfluenceScoreAsync(string walletAddress)
    {
        var query = await _whaleMovementRepository.GetQueryableAsync();
        var historical = query.Where(m => m.WalletAddress == walletAddress && m.PriceAfter4h.HasValue).ToList();

        if (!historical.Any()) return 0.5; // Default score for new whales

        int successfulMoves = 0;
        foreach (var move in historical)
        {
            decimal priceChange = (move.PriceAfter4h.Value - move.PriceAtMovement) / move.PriceAtMovement;
            
            // If accumulation/inflow led to price rise (>1.5%) -> Success
            if ((move.MovementType == "Inflow" || move.MovementType == "Accumulation") && priceChange > 0.015m)
                successfulMoves++;
            // If distribution/outflow led to price drop (<-1.5%) -> Success
            else if ((move.MovementType == "Outflow" || move.MovementType == "Distribution") && priceChange < -0.015m)
                successfulMoves++;
        }

        return Math.Round((double)successfulMoves / historical.Count, 2);
    }
}
