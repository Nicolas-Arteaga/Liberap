using System.Collections.Generic;

namespace Verge.Freqtrade
{
    public class FreqtradeStatusDto
    {
        public bool IsRunning { get; set; }
        public List<string> ActivePairs { get; set; } = new();
        public int OpenTradesCount { get; set; }
        public long RuntimeSeconds { get; set; }
    }
}
