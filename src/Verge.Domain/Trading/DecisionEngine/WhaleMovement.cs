using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading.DecisionEngine;

public class WhaleMovement : FullAuditedEntity<Guid>
{
    public string Symbol { get; set; }
    public string WalletAddress { get; set; }
    public decimal Amount { get; set; }
    public decimal PriceAtMovement { get; set; }
    public string MovementType { get; set; } // "Inflow", "Outflow", "Accumulation", "Distribution"
    public DateTime Timestamp { get; set; }
    
    // Correlation Tracking
    public decimal? PriceAfter4h { get; set; }
    public double InfluenceScore { get; set; } // 0.0 to 1.0 (Calculated based on price impact)
    public bool WasMarketMover { get; set; }

    protected WhaleMovement() { }

    public WhaleMovement(Guid id, string symbol, string walletAddress, decimal amount, decimal priceAtMovement, string movementType)
        : base(id)
    {
        Symbol = symbol;
        WalletAddress = walletAddress;
        Amount = amount;
        PriceAtMovement = priceAtMovement;
        MovementType = movementType;
        Timestamp = DateTime.UtcNow;
        InfluenceScore = 0.5; // Starting neutral
    }
}
