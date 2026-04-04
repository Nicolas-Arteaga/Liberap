namespace Verge.Freqtrade
{
    public class FreqtradeProfitDto
    {
        public decimal TotalProfit { get; set; }
        public decimal TodayProfit { get; set; }
        public decimal WinRate { get; set; }
        public int TotalTrades { get; set; }
    }
}
