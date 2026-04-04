using System.ComponentModel.DataAnnotations;

namespace Verge.Freqtrade
{
    public class FreqtradeCreateBotDto
    {
        [Required]
        public string Pair { get; set; }

        [Required]
        public string Timeframe { get; set; }

        [Required]
        public decimal StakeAmount { get; set; }

        public decimal TpPercent { get; set; }

        public decimal SlPercent { get; set; }

        public int Leverage { get; set; }

        public string Strategy { get; set; } = "VergeFreqAIStrategy";
    }
}
