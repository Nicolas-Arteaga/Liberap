using System;

namespace Verge.Freqtrade
{
    public class FreqtradeTradeDto
    {
        public int Id { get; set; }
        public string Pair { get; set; }
        public decimal Amount { get; set; }
        public decimal OpenRate { get; set; }
        public decimal CurrentRate { get; set; }
        public decimal Pnl { get; set; }
        public decimal ProfitPercentage { get; set; }
        public decimal ProfitAbs { get; set; }
        public DateTime OpenDate { get; set; }
        public DateTime? CloseDate { get; set; }
        public bool IsShort { get; set; }
    }
}
