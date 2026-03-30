using System;

namespace Verge.Trading.Bot;

public class BotActivityLogDto
{
    public string Symbol { get; set; } = string.Empty;
    public string Message { get; set; } = string.Empty;
    public string Type { get; set; } = string.Empty;
    public DateTime Timestamp { get; set; }
}
