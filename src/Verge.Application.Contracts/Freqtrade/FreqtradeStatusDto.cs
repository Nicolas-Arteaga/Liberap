namespace Verge.Freqtrade
{
    public class FreqtradeStatusDto
    {
        public bool IsRunning { get; set; }
        public string CurrentPair { get; set; }
        public int OpenTradesCount { get; set; }
        public long RuntimeSeconds { get; set; }
    }
}
