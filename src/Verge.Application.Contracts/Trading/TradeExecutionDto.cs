using System;

namespace Verge.Trading
{
    public class TradePreviewDto
    {
        public string Symbol { get; set; }
        public string Side { get; set; }
        public decimal Quantity { get; set; }
        public decimal EstimatedPrice { get; set; }
        public decimal NotionalValue => Quantity * EstimatedPrice;
        public decimal EstimatedFee => NotionalValue * 0.0004m; // Binance Futures 0.04%
        public string ConfirmationToken { get; set; }
    }

    public class TradeRequestDto
    {
        public string Symbol { get; set; }
        public string Side { get; set; }
        public decimal Quantity { get; set; }
        public int Leverage { get; set; } = 3;
    }

    public class TradeConfirmationDto
    {
        public string ConfirmationToken { get; set; }
    }
}
