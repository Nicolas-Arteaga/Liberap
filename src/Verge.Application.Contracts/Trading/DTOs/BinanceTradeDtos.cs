using System;

namespace Verge.Trading.DTOs
{
    public class OpenBinanceTradeInputDto
    {
        public string Symbol { get; set; } = string.Empty;
        public string Side { get; set; } = string.Empty; // "BUY" / "SELL" (or "0" / "1")
        public decimal Quantity { get; set; }
        public decimal? TpPrice { get; set; }
        public decimal? SlPrice { get; set; }
    }

    public class CloseBinanceTradeInputDto
    {
        public string Symbol { get; set; } = string.Empty;
    }

    public class BinanceTradeResultDto
    {
        public bool Success { get; set; }
        public string Message { get; set; } = string.Empty;
    }
}
