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
        public DateTime OpenDate { get; set; }
    }
}
